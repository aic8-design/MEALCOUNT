import streamlit as st
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- 구글 시트 연동 설정 ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Streamlit Secrets에서 보안 키 불러오기
try:
key_dict = json.loads(st.secrets["gcp_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)

client = gspread.authorize(creds)
doc = client.open_by_key("1Je9nGeVC2aKossXKI_7uUwHOL3ZHEpDFI_ReUEoWR-c")

except Exception as e:
    st.error(f"구글 시트 연결 오류: {e}")
    st.stop()

# --- UI 설정 ---
st.set_page_config(page_title="HAAC 식수 신청", layout="wide")
st.title("🍽️ HAAC 현장 식수 신청 시스템")

# 1. 날짜 및 팀 선택
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("식사 일자 선택", datetime.date.today())
with col2:
    # 이미지 기반 팀 리스트
    team_list = ['R/U', 'QM', '기계', 'PAC', '전장', '전장(자재)', '냉각기', '두산', '자재', '수소파트', 'AS']
    selected_team = st.selectbox("소속팀 선택", team_list)

# 마감 시간 체크 로직
now = datetime.datetime.now()
is_lunch_closed = (target_date == now.date() and now.hour >= 9) or (target_date < now.date())
dinner_deadline = target_date - datetime.timedelta(days=3)
is_dinner_closed = (now.date() > dinner_deadline) or (now.date() == dinner_deadline and now.hour >= 14)

st.info(f"📅 선택 날짜: {target_date} | ⏰ 현재 시간: {now.strftime('%H:%M')}")

# 2. 구글 시트에서 '명단' 불러오기
@st.cache_data(ttl=600) # 10분간 캐시 유지 (성능 향상)
def load_members():
    try:
        member_sheet = doc.worksheet("명단")
        data = member_sheet.get_all_records()
        return pd.DataFrame(data)
    except:
        st.error("'명단' 시트를 찾을 수 없습니다. (A열: 소속, B열: 사번, C열: 직책, D열: 이름 필수)")
        return pd.DataFrame()

all_members_df = load_members()

if not all_members_df.empty:
    # 선택된 팀원만 필터링
    filtered_df = all_members_df[all_members_df['소속'] == selected_team].copy()
    
    # 직책 순서 정렬 (팀장-조장-사원-외국인)
    sort_priority = {'팀장': 1, '조장': 2, '사원': 3, '외국인': 4}
    filtered_df['priority'] = filtered_df['직책'].map(sort_priority).fillna(99)
    filtered_df = filtered_df.sort_values('priority').drop(columns=['priority'])
    
    # 신청 체크박스 컬럼 초기화 (기본값 False)
    filtered_df['중식'] = False
    filtered_df['석식'] = False

    st.write(f"### 👥 {selected_team} 명단 (총 {len(filtered_df)}명)")
    
    # 🔥 핵심: key에 날짜와 팀을 넣어 변경 시 자동 초기화되도록 설정
    editor_key = f"editor_{target_date}_{selected_team}"
    
    edited_df = st.data_editor(
        filtered_df,
        key=editor_key,
        hide_index=True,
        column_config={
            "소속": st.column_config.TextColumn(disabled=True),
            "사번": st.column_config.TextColumn(disabled=True),
            "직책": st.column_config.TextColumn(disabled=True),
            "이름": st.column_config.TextColumn(disabled=True),
            "중식": st.column_config.CheckboxColumn(required=True),
            "석식": st.column_config.CheckboxColumn(required=True),
        },
        use_container_width=True
    )

    # 3. 신청서 제출 버튼
    if st.button("🍽️ 식수 신청하기", type="primary", use_container_width=True):
        lunch_list = edited_df[edited_df['중식'] == True][['소속', '사번', '직책', '이름']].values.tolist()
        dinner_list = edited_df[edited_df['석식'] == True][['소속', '사번', '직책', '이름']].values.tolist()
        
        try:
            # 중식 기록
            if not is_lunch_closed and lunch_list:
                doc.worksheet("중식").append_rows(lunch_list)
                st.success(f"✅ 중식 {len(lunch_list)}명 신청 완료!")
            elif is_lunch_closed and lunch_list:
                st.error("❌ 중식 마감시간(09시)이 지났습니다.")
                
            # 석식 기록
            if not is_dinner_closed and dinner_list:
                doc.worksheet("석식").append_rows(dinner_list)
                st.success(f"✅ 석식 {len(dinner_list)}명 신청 완료!")
            elif is_dinner_closed and dinner_list:
                st.error("❌ 석식 마감시간(3일전 14시)이 지났습니다.")
                
            if not lunch_list and not dinner_list:
                st.warning("신청 인원을 체크해 주세요.")
                
        except Exception as e:
            st.error(f"저장 중 오류 발생: {e}")
else:
    st.warning("스프레드시트에서 명단 데이터를 가져올 수 없습니다.")