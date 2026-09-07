import streamlit as st

st.set_page_config(page_title="부동산 자산관리 앱", layout="wide", page_icon="🏢")

pages = {
    '📊 부동산 자산관리 앱': [
        st.Page('pages/01_master_dashboard.py', title='Master Dashboard'),
        st.Page('pages/02_market_research.py', title='Market Research'),
        st.Page('pages/03_asset_view.py', title='Asset View'),
        st.Page('pages/04_stacking_plan.py', title='Stacking Plan'),
        st.Page('pages/05_lease_info.py', title='Lease Info'),
        st.Page('pages/06_rent_roll.py', title='Rent Roll'),
        st.Page('pages/07_rent_change.py', title='Rent Change'),
        st.Page('pages/08_asset_update.py', title='Asset Update'),
        st.Page('pages/09_contract_update.py', title='Contract Update'),
        st.Page('pages/10_history.py', title='History'),
    ]
}

pg = st.navigation(pages)
pg.run()
