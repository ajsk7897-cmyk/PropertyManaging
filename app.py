import streamlit as st

st.set_page_config(page_title="부동산 자산관리 앱", layout="wide", page_icon="🏢")

pages = {
    '📊 부동산 자산관리 앱': [
        st.Page('pages/01_마스터_대시보드.py', title='마스터 대시보드'),
        st.Page('pages/02_시장_동향_리서치.py', title='시장 동향 리서치'),
        st.Page('pages/03_자산별_통합_조회.py', title='자산별 통합 조회'),
        st.Page('pages/04_스태킹_플랜.py', title='스태킹 플랜'),
        st.Page('pages/05_임대차_계약_조회.py', title='임대차 계약 조회'),
        st.Page('pages/06_렌트롤_관리.py', title='렌트롤 관리'),
        st.Page('pages/07_임대료_변동_추이.py', title='임대료 변동 추이'),
        st.Page('pages/08_자산_정보_업데이트.py', title='자산 정보 업데이트'),
        st.Page('pages/09_계약_정보_업데이트.py', title='계약 정보 업데이트'),
        st.Page('pages/10_계약_변경_이력.py', title='계약 변경 이력'),
    ]
}

from utils import render_sidebar_notifications

with st.sidebar:
    render_sidebar_notifications()

pg = st.navigation(pages)
pg.run()
