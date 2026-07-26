import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("📉 임대료 및 관리비 변동 현황 (전월 대비)")
    
today = datetime.now()
    
col_y, col_m = st.columns([1, 1])
with col_y:
    sel_year = st.selectbox(
        "기준 연도", 
        list(range(2024, 2031)), 
        index=list(range(2024, 2031)).index(today.year) if today.year in range(2024, 2031) else 2, 
        key="rc_year"
    )
with col_m:
    sel_month = st.selectbox(
        "기준 월", 
        list(range(1, 13)), 
        index=today.month - 1, 
        key="rc_month"
    )
        
this_month = datetime(sel_year, sel_month, 1)
last_month = (this_month - timedelta(days=1)).replace(day=1)
    
if this_month.month == 12:
    this_month_end = datetime(this_month.year, 12, 31)
else:
    this_month_end = datetime(this_month.year, this_month.month + 1, 1) - timedelta(days=1)
    
st.markdown(f"**기준월**: {this_month.strftime('%Y년 %m월')} (비교: {last_month.strftime('%Y년 %m월')})")
    
df_contracts_all = fetch_data("SELECT * FROM Lease_Contracts")
    
change_records = []
if not df_contracts_all.empty:
    for _, row in df_contracts_all.iterrows():
        start_date_str = row.get("start_date")
        end_date_str = row.get("end_date")
            
        if pd.isna(start_date_str) or pd.isna(end_date_str) or not start_date_str or not end_date_str:
            continue
                
        c_start = pd.to_datetime(start_date_str)
        c_end = pd.to_datetime(end_date_str)
            
        # Check if contract was active during last_month or this_month
        if c_start > this_month_end or c_end < last_month:
            continue
                
        cid = row["contract_id"]
        company = row["company_name"]
        asset = row["asset_name"]
        floor = row["floor"]
        currency = row.get("currency", "KRW")
        if pd.isna(currency):
            currency = "KRW"
            
        def_rent = float(row.get("monthly_rent", 0) if pd.notna(row.get("monthly_rent")) else 0)
        def_maint = float(row.get("monthly_maintenance_fee", 0) if pd.notna(row.get("monthly_maintenance_fee")) else 0)
            
        rent_schedule = row.get("rent_schedule", "")
            
        last_rent, last_maint = get_scheduled_amount(rent_schedule, last_month, def_rent, def_maint, currency)
        this_rent, this_maint = get_scheduled_amount(rent_schedule, this_month, def_rent, def_maint, currency)
            
        # 절사 로직 제외된 정확한 값으로 비교
        if str(last_rent) != str(this_rent) or str(last_maint) != str(this_maint):
            change_type = []
            if last_rent != this_rent:
                change_type.append("임대료 인상" if this_rent > last_rent else "임대료 인하")
            if last_maint != this_maint:
                change_type.append("관리비 인상" if this_maint > last_maint else "관리비 인하")
                
            change_records.append({
                "업체명": company,
                "자산명": asset,
                "층": floor,
                "기존 임대료": last_rent,
                "기존 관리비": last_maint,
                "변경 임대료": this_rent,
                "변경 관리비": this_maint,
                "변경 내용": ", ".join(change_type),
                "통화": currency
            })
    
if change_records:
    df_changes = pd.DataFrame(change_records)
    df_changes = df_changes[["자산명", "층", "업체명", "기존 임대료", "변경 임대료", "기존 관리비", "변경 관리비", "변경 내용", "통화"]]
        
    csv_changes = generate_formatted_excel(df_changes, [])
        
    col_c1, col_c2 = st.columns([7, 3], vertical_alignment="bottom")
    with col_c1:
        st.markdown("### 상세 변동 내역")
    with col_c2:
        st.download_button(
            label="📥 엑셀 다운로드",
            data=csv_changes,
            file_name=f"Rent_Changes_{today.strftime('%Y%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_rent_changes",
            use_container_width=True
        )
            
    display_styled_table(df_changes, freeze_cols=1)
else:
    st.info("이번 달 임대료 및 관리비 변동 내역이 없습니다.")


# ==========================================
# Tab 4: 자산정보 업데이트
# ==========================================
