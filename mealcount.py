import streamlit as st
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pytz

# --- 대한민국 시간대 설정 ---
KST = pytz.timezone('Asia/Seoul')
now_kst = datetime.datetime.now(KST)
today_kst = now_kst.date()

# --- 구글 시트 연동 설정 ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_gspread_client():
    try:
        key_dict = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"구글 인증 오류: {e}")
        return None

client = get_gspread_client()

if client:
    try:
        spreadsheet_key = "1Je9nGeVC2aKossXKI_7uUwHOL3ZHEpDFI_ReUEoWR-c"
        doc = client.open_by_key(spreadsheet_key)
    except Exception as e:
        st.error(f"스프레드시트를 찾을 수 없습니다: {e}")
        st.stop()
else:
    st.stop()

# --- UI 설정 ---
st.set_page_config(page_title="HAAC 식수 신청", layout="wide")
st.title("🍽️ HAAC 현장 식수 신청 시스템")

# 1. 날짜 및 팀 선택
col1, col2 = st.columns(2)
with col1:
    # 기본값을 한국 오늘 날짜로 설정
    target_date = st.date_input("식사 일자 선택", today_kst)
with col2:
    team_list = ['R/U', 'QM', '기계', 'PAC', '전장', '전장(자재)', '냉각기', '두산', '자재', '수소파트', 'AS']
    selected_team = st.selectbox("소속팀 선택", team_list)

# 마감 시간 체크 (now_kst 사용)
is_lunch_closed = (target_date == today_kst and now_kst.hour >= 9) or (target_date < today_kst)
dinner_deadline_date = target_date - datetime.timedelta(days=3)
is_dinner_closed = (now_kst.date() > dinner_deadline_date) or (now_kst.date() == dinner_deadline_date and now_kst.hour >= 14)

st.info(f"📅 선택 날짜: {target_date} | ⏰ 현재 서울 시간: {now_kst.strftime('%H:%M')}")

# 마감 안내 메시지
if is_lunch_closed:
    st.warning("⚠️ 중식 신청이 마감되었습니다. (당일 09:00 마감)")
if is_dinner_closed:
    st.warning("⚠️ 석식 신청이 마감되었습니다. (3일 전 14:00 마감)")

# 2. "명단" 시트에서 데이터 불러오기
try:
    member_sheet = doc.worksheet("명단")
    all_data = pd.DataFrame(member_sheet.get_all_records())
except Exception as e:
    st.error(f"'명단' 시트를 불러오지 못했습니다: {e}")
    st.stop()

if not all_data.empty:
    # 해당 팀원 필터링 및 정렬
    df = all_data[all_data['소속'] == selected_team].copy()
    sort_priority = {'팀장': 1, '조장': 2, '사원': 3, '외국인': 4}
    df['priority'] = df['직책'].map(sort_priority).fillna(99)
    df = df.sort_values('priority').drop(columns=['priority']).reset_index(drop=True)
    
    st.write(f"### 👥 {selected_team} 명단")

    # --- 전체 선택 기능 ---
    sel_col1, sel_col2, _ = st.columns([1, 1, 4])
    with sel_col1:
        select_all_lunch = st.checkbox("중식 전체 선택", disabled=is_lunch_closed)
    with sel_col2:
        select_all_dinner = st.checkbox("석식 전체 선택", disabled=is_dinner_closed)

    # 데이터프레임에 초기값 반영
    df['중식'] = select_all_lunch
    df['석식'] = select_all_dinner

    # --- 데이터 에디터 (표) ---
    # 날짜나 팀이 바뀌면 에디터 상태를 초기화하기 위한 key 설정
    editor_key = f"editor_{target_date}_{selected_team}_{select_all_lunch}_{select_all_dinner}"
    
    edited_df = st.data_editor(
        df,
        key=editor_key,
        hide_index=True,
        use_container_width=True,
        column_config={
            "소속": st.column_config.TextColumn(disabled=True),
            "사번": st.column_config.TextColumn(disabled=True),
            "직책": st.column_config.TextColumn(disabled=True),
            "이름": st.column_config.TextColumn(disabled=True),
            "중식": st.column_config.CheckboxColumn(
                "중식",
                help="마감 전까지 체크 가능",
                disabled=is_lunch_closed # 마감 시 체크 불가
            ),
            "석식": st.column_config.CheckboxColumn(
                "석식",
                help="3일 전 14:00까지 체크 가능",
                disabled=is_dinner_closed # 마감 시 체크 불가
            ),
        }
    )

    # 3. 신청서 제출
    if st.button("🍽️ 식수 신청하기", type="primary", use_container_width=True):
        lunch_people = edited_df[edited_df['중식'] == True][['소속', '사번', '직책', '이름']]
        dinner_people = edited_df[edited_df['석식'] == True][['소속', '사번', '직책', '이름']]
        
        lunch_people.insert(0, '식사일자', str(target_date))
        dinner_people.insert(0, '식사일자', str(target_date))

        try:
            if not is_lunch_closed and not lunch_people.empty:
                doc.worksheet("중식").append_rows(lunch_people.values.tolist())
                st.success(f"✅ 중식 {len(lunch_people)}명 신청 완료")
                
            if not is_dinner_closed and not dinner_people.empty:
                doc.worksheet("석식").append_rows(dinner_people.values.tolist())
                st.success(f"✅ 석식 {len(dinner_people)}명 신청 완료")
                
            if lunch_people.empty and dinner_people.empty:
                st.warning("선택된 인원이 없습니다.")
        except Exception as e:
            st.error(f"저장 오류: {e}")