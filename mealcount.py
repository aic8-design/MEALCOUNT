import streamlit as st
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

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
        # 제공해주신 시트 ID로 직접 엽니다.
        spreadsheet_key = "1Je9nGeVC2aKossXKI_7uUwHOL3ZHEpDFI_ReUEoWR-c"
        doc = client.open_by_key(spreadsheet_key)
    except Exception as e:
        st.error(f"스프레드시트를 찾을 수 없습니다. ID와 공유 설정을 확인해주세요: {e}")
        st.stop()
else:
    st.stop()

# --- UI 설정 ---
st.set_page_config(page_title="HAAC 식수 신청", layout="wide")
st.title("🍽️ HAAC 현장 식수 신청 시스템")

# 1. 날짜 및 팀 선택
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("식사 일자 선택", datetime.date.today())
with col2:
    team_list = ['R/U', 'QM', '기계', 'PAC', '전장', '전장(자재)', '냉각기', '두산', '자재', '수소파트', 'AS']
    selected_team = st.selectbox("소속팀 선택", team_list)

# 마감 시간 체크 로직
now = datetime.datetime.now()
is_lunch_closed = (target_date == now.date() and now.hour >= 9) or (target_date < now.date())
dinner_deadline = target_date - datetime.timedelta(days=3)
is_dinner_closed = (now.date() > dinner_deadline) or (now.date() == dinner_deadline and now.hour >= 14)

st.info(f"📅 선택 날짜: {target_date} | ⏰ 현재 시간: {now.strftime('%H:%M')}")

# 2. "명단" 시트에서 데이터 불러오기
try:
    member_sheet = doc.worksheet("명단")
    all_data = pd.DataFrame(member_sheet.get_all_records())
except Exception as e:
    st.error(f"'명단' 시트를 불러오지 못했습니다: {e}")
    st.info("💡 팁: 구글 시트 하단 탭 이름이 정확히 '명단'인지 확인해 주세요.")
    st.stop()

if not all_data.empty:
    # 선택된 팀원 필터링 및 정렬
    df = all_data[all_data['소속'] == selected_team].copy()
    sort_priority = {'팀장': 1, '조장': 2, '사원': 3, '외국인': 4}
    df['priority'] = df['직책'].map(sort_priority).fillna(99)
    df = df.sort_values('priority').drop(columns=['priority'])
    
    # 체크박스 컬럼 추가 (날짜/팀 변경 시 초기화되도록 key 설정)
    df['중식'] = False
    df['석식'] = False

    st.write(f"### 👥 {selected_team} 명단")
    
    # 에디터 key에 날짜와 팀을 조합하여 상태 초기화 유도
    editor_key = f"editor_{target_date}_{selected_team}"
    edited_df = st.data_editor(
        df,
        key=editor_key,
        hide_index=True,
        use_container_width=True,
        disabled=['소속', '사번', '직책', '이름']
    )

    # 3. 신청서 제출
    if st.button("🍽️ 식수 신청하기", type="primary", use_container_width=True):
        # 체크된 인원 추출
        lunch_people = edited_df[edited_df['중식'] == True][['소속', '사번', '직책', '이름']]
        dinner_people = edited_df[edited_df['석식'] == True][['소속', '사번', '직책', '이름']]
        
        # 신청 일자 정보 추가 (자동화 서버 집계용)
        lunch_people.insert(0, '신청일자', str(target_date))
        dinner_people.insert(0, '신청일자', str(target_date))

        try:
            # 중식 저장
            if not is_lunch_closed and not lunch_people.empty:
                doc.worksheet("중식").append_rows(lunch_people.values.tolist())
                st.success(f"✅ 중식 {len(lunch_people)}명 완료")
            elif is_lunch_closed and not lunch_people.empty:
                st.error("❌ 중식 마감(09:00)")

            # 석식 저장
            if not is_dinner_closed and not dinner_people.empty:
                doc.worksheet("석식").append_rows(dinner_people.values.tolist())
                st.success(f"✅ 석식 {len(dinner_people)}명 완료")
            elif is_dinner_closed and not dinner_people.empty:
                st.error("❌ 석식 마감(3일전 14:00)")
                
            if lunch_people.empty and dinner_people.empty:
                st.warning("신청할 인원을 선택해 주세요.")

        except Exception as e:
            st.error(f"시트 저장 오류: {e}")