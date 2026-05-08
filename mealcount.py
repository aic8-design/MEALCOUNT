import streamlit as st
import pandas as pd
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json # json 라이브러리 추가 필수!

# --- 구글 시트 연동 설정 ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# (수정된 부분) Streamlit Secrets에서 데이터를 가져와 딕셔너리로 변환
key_dict = json.loads(st.secrets["gcp_service_account"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)

client = gspread.authorize(creds)
doc = client.open("HAAC 현장 식수 집계")

# --- UI 및 로직 ---
st.title("🍽️ HAAC 현장 식수 신청 시스템")

# 1. 날짜 및 팀 선택
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("식사 일자 선택", datetime.date.today())
with col2:
    team_list = ['R/U', 'QM', '기계', 'PAC', '전장', '전장(자재), '냉각기', '두산', '자재', '수소파트', 'AS']
    selected_team = st.selectbox("소속팀 선택", team_list)

# 마감 시간 체크 로직 (중식: 당일 09시, 석식: 3일전 14시)
now = datetime.datetime.now()
is_lunch_closed = (target_date == now.date() and now.hour >= 9) or (target_date < now.date())
dinner_deadline = target_date - datetime.timedelta(days=3)
is_dinner_closed = (now.date() > dinner_deadline) or (now.date() == dinner_deadline and now.hour >= 14)

st.info(f"선택한 날짜: {target_date} | 현재 시간: {now.strftime('%Y-%m-%d %H:%M')}")

# 2. 명단 불러오기 (임시 데이터 프레임 예시 - 실제로는 '명단' 시트에서 불러오는 것을 권장)
# sheet_members = doc.worksheet("명단").get_all_records()
# df = pd.DataFrame(sheet_members)
# df = df[df['소속'] == selected_team]

# 임시 데이터 (테스트용)
data = {
    '소속': [selected_team]*4,
    '사번': ['1001', '1002', '1003', '1004'],
    '직책': ['팀장', '사원', '외국인', '조장'],
    '이름': ['김팀장', '이홍길', '존슨', '박조장']
}
df = pd.DataFrame(data)

# 직책 순서 정렬 (팀장-조장-사원-외국인)
sort_map = {'팀장': 1, '조장': 2, '사원': 3, '외국인': 4}
df['정렬순위'] = df['직책'].map(sort_map).fillna(99)
df = df.sort_values('정렬순위').drop(columns=['정렬순위']).reset_index(drop=True)

# 신청 체크박스 컬럼 추가
df['중식 신청'] = False
df['석식 신청'] = False

st.write(f"### 👥 {selected_team} 명단")
# data_editor를 통해 체크박스 직접 수정 가능하게 구현
edited_df = st.data_editor(df, hide_index=True, disabled=['소속', '사번', '직책', '이름'])

if st.button("신청서 제출", type="primary"):
    # 신청한 인원만 필터링
    lunch_df = edited_df[edited_df['중식 신청'] == True][['소속', '사번', '직책', '이름']]
    dinner_df = edited_df[edited_df['석식 신청'] == True][['소속', '사번', '직책', '이름']]
    
    try:
        # 중식 저장
        if not is_lunch_closed and not lunch_df.empty:
            lunch_sheet = doc.worksheet("중식")
            lunch_sheet.append_rows(lunch_df.values.tolist())
            st.success(f"✅ 중식 {len(lunch_df)}명 신청 완료!")
        elif is_lunch_closed and not lunch_df.empty:
            st.error("❌ 중식 신청이 마감되었습니다. (당일 09시 마감)")
            
        # 석식 저장
        if not is_dinner_closed and not dinner_df.empty:
            dinner_sheet = doc.worksheet("석식")
            dinner_sheet.append_rows(dinner_df.values.tolist())
            st.success(f"✅ 석식 {len(dinner_df)}명 신청 완료!")
        elif is_dinner_closed and not dinner_df.empty:
            st.error("❌ 석식 신청이 마감되었습니다. (3일전 14시 마감)")
            
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")