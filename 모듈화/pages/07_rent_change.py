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
rf_records = []
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
            
        from 모듈화.utils import get_actual_monthly_rent_by_company
        
        # 1) 기본 임대료 변동 (렌트프리 무시)
        last_rent_base, last_maint_base = get_actual_monthly_rent_by_company(df_contracts_all, asset, floor, company, last_month.year, last_month.month, ignore_rent_free=True)
        this_rent_base, this_maint_base = get_actual_monthly_rent_by_company(df_contracts_all, asset, floor, company, this_month.year, this_month.month, ignore_rent_free=True)
        
        # Apply Overrides if any contract belonging to this company has one
        active_contracts = df_contracts_all[
            (df_contracts_all['asset_name'] == asset) &
            (df_contracts_all['floor'] == floor) &
            (df_contracts_all['company_name'] == company)
        ]
        
        has_rf_this_month = False
        rf_saved_rent = 0.0
        
        for _, rc in active_contracts.iterrows():
            cid = rc["contract_id"]
            if (cid, floor) in overrides_last_dict:
                last_rent_base, last_maint_base = overrides_last_dict[(cid, floor)]
            if (cid, floor) in overrides_this_dict:
                this_rent_base, this_maint_base = overrides_this_dict[(cid, floor)]
            
            # 렌트프리 여부 확인 (계약정보 업데이트 시 입력된 JSON 기반)
            rf_list = rc.get("rent_free_details", "[]")
            if pd.notna(rf_list) and rf_list:
                try:
                    rfs = json.loads(rf_list)
                    month_str = this_month.strftime("%Y-%m")
                    if month_str in rfs:
                        has_rf_this_month = True
                except:
                    pass
                    
        if currency != "KRW":
            last_rent_base = round(last_rent_base, 2)
            last_maint_base = round(last_maint_base, 2)
            this_rent_base = round(this_rent_base, 2)
            this_maint_base = round(this_maint_base, 2)
            
        # 렌트프리 내역 추가
        if has_rf_this_month and (this_rent_base > 0 or this_maint_base > 0):
            rf_records.append({
                "자산명": asset,
                "층": floor,
                "업체명": company,
                "절감 임대료": this_rent_base,
                "절감 관리비": 0.0,
                "통화": currency
            })
            
        if last_rent_base == 0 and last_maint_base == 0 and this_rent_base == 0 and this_maint_base == 0:
            continue
            
        if str(last_rent_base) != str(this_rent_base) or str(last_maint_base) != str(this_maint_base):
            change_type = []
            if last_rent_base != this_rent_base:
                if this_rent_base > last_rent_base:
                    change_type.append("임대료 정기인상/갱신")
                else:
                    change_type.append("임대료 인하")
                    
            if last_maint_base != this_maint_base:
                if this_maint_base > last_maint_base:
                    change_type.append("관리비 정기인상/갱신")
                else:
                    change_type.append("관리비 인하")
                
            change_records.append({
                "업체명": company,
                "자산명": asset,
                "층": floor,
                "기존 임대료": last_rent_base,
                "기존 관리비": last_maint_base,
                "변경 임대료": this_rent_base,
                "변경 관리비": this_maint_base,
                "변경 내용": ", ".join(change_type),
                "통화": currency
            })

if change_records:
    df_changes = pd.DataFrame(change_records)
    df_changes = df_changes[["자산명", "층", "업체명", "기존 임대료", "변경 임대료", "기존 관리비", "변경 관리비", "변경 내용", "통화"]]
    
    csv_changes = generate_formatted_excel(df_changes, [])
    
    col_c1, col_c2 = st.columns([7, 3], vertical_alignment="bottom")
    with col_c1:
        st.markdown("### 📈 임대료 및 관리비 변동 내역 (렌트프리 제외)")
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
    st.info("이번 달 정기인상 및 갱신에 따른 임대료 변동 내역이 없습니다.")
    
st.markdown("---")

if rf_records:
    df_rf = pd.DataFrame(rf_records)
    df_rf = df_rf[["자산명", "층", "업체명", "절감 임대료", "통화"]]
    
    csv_rf = generate_formatted_excel(df_rf, [])
    
    col_r1, col_r2 = st.columns([7, 3], vertical_alignment="bottom")
    with col_r1:
        st.markdown("### 🎁 당월 렌트프리 적용 내역")
    with col_r2:
        st.download_button(
            label="📥 엑셀 다운로드",
            data=csv_rf,
            file_name=f"Rent_Free_{today.strftime('%Y%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_rent_free",
            use_container_width=True
        )
        
    display_styled_table(df_rf, freeze_cols=1)
else:
    st.info("이번 달 렌트프리가 적용되는 업체가 없습니다.")


# ==========================================
# Tab 4: 자산정보 업데이트
# ==========================================
