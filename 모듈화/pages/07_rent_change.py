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
    unique_groups = df_contracts_all[["asset_name", "floor", "company_name", "currency"]].drop_duplicates()
    
    # Pre-fetch manual overrides
    df_overrides_last = fetch_data(f"SELECT * FROM RentRoll_Overrides WHERE year = {last_month.year} AND month = {last_month.month}")
    df_overrides_this = fetch_data(f"SELECT * FROM RentRoll_Overrides WHERE year = {this_month.year} AND month = {this_month.month}")
    
    overrides_last_dict = {}
    if not df_overrides_last.empty:
        for _, ov in df_overrides_last.iterrows():
            overrides_last_dict[(ov["contract_id"], ov["floor"])] = (ov["over_rent"], ov["over_maint"])
            
    overrides_this_dict = {}
    if not df_overrides_this.empty:
        for _, ov in df_overrides_this.iterrows():
            overrides_this_dict[(ov["contract_id"], ov["floor"])] = (ov["over_rent"], ov["over_maint"])
            
    for _, group in unique_groups.iterrows():
        asset = group["asset_name"]
        floor = group["floor"]
        company = group["company_name"]
        currency = group["currency"]
        if pd.isna(currency) or not currency:
            currency = "KRW"
            
        last_rent, last_maint = get_actual_monthly_rent_by_company(df_contracts_all, asset, floor, company, last_month.year, last_month.month)
        this_rent, this_maint = get_actual_monthly_rent_by_company(df_contracts_all, asset, floor, company, this_month.year, this_month.month)
        
        # Apply Overrides if any contract belonging to this company has one
        active_contracts = df_contracts_all[
            (df_contracts_all['asset_name'] == asset) &
            (df_contracts_all['floor'] == floor) &
            (df_contracts_all['company_name'] == company)
        ]
        for _, rc in active_contracts.iterrows():
            cid = rc["contract_id"]
            if (cid, floor) in overrides_last_dict:
                last_rent, last_maint = overrides_last_dict[(cid, floor)]
            if (cid, floor) in overrides_this_dict:
                this_rent, this_maint = overrides_this_dict[(cid, floor)]
                
        if currency != "KRW":
            last_rent = round(last_rent, 2)
            last_maint = round(last_maint, 2)
            this_rent = round(this_rent, 2)
            this_maint = round(this_maint, 2)
            
        if last_rent == 0 and last_maint == 0 and this_rent == 0 and this_maint == 0:
            continue
            
        if str(last_rent) != str(this_rent) or str(last_maint) != str(this_maint):
            change_type = []
            if last_rent != this_rent:
                if this_rent == 0 and last_rent > 0:
                    change_type.append("임대료 인하 (당월 렌트프리)")
                elif last_rent == 0 and this_rent > 0:
                    change_type.append("임대료 인상 (렌트프리 종료)")
                elif this_rent > last_rent:
                    change_type.append("임대료 인상")
                else:
                    change_type.append("임대료 인하")
                    
            if last_maint != this_maint:
                if this_maint == 0 and last_maint > 0:
                    change_type.append("관리비 인하 (면제)")
                elif last_maint == 0 and this_maint > 0:
                    change_type.append("관리비 인상 (면제 종료)")
                elif this_maint > last_maint:
                    change_type.append("관리비 인상")
                else:
                    change_type.append("관리비 인하")
                
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
