import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("자산별 스태킹 플랜 (Visual Stacking Plan)")

# Needs assets list
df_asset_sp = fetch_data("SELECT DISTINCT asset_name FROM Asset_Area")
if not df_asset_sp.empty:
    assets_sp = df_asset_sp["asset_name"].tolist()
# --- Visual Stacking Plan ---
st.markdown("---")
st.subheader("🏢 자산별 스태킹 플랜 (Visual Stacking Plan)")

# Select single asset for stacking plan
sp_asset = st.selectbox("스태킹 플랜을 조회할 자산을 선택하세요", options=assets)

if sp_asset:
    unit_sp = st.radio(
        "🔄 표출 면적 단위 선택",
        ["평", "㎡", "sqft"],
        horizontal=True,
        key="sp_unit_radio",
    )
    mult = 1.0
    if unit_sp == "㎡":
        mult = CURRENCY_RATES["PY_TO_SQM"]
    elif unit_sp == "sqft":
        mult = CURRENCY_RATES["PY_TO_SF"]

    # Get floors for this asset
    df_floors = fetch_data(
        f"SELECT floor, exclusive_area, bank_area FROM Asset_Area WHERE asset_name = '{sp_asset}'",
        _eng=engine
    )
        
    df_leases_sp = fetch_data(
        f"SELECT floor, company_name, contract_area FROM Lease_Contracts WHERE asset_name = '{sp_asset}' AND status = 'ACTIVE' AND start_date <= '{today_str}' AND end_date >= '{today_str}'",
        _eng=engine
    )

    # Sort floors dynamically
    def floor_sort_key(f):
        f = str(f).upper()
        if f.startswith("B"):
            try:
                return -int("".join(filter(str.isdigit, f)))
            except:
                return -99
        else:
            try:
                return int("".join(filter(str.isdigit, f)))
            except:
                return 0

    df_floors["sort_key"] = df_floors["floor"].apply(floor_sort_key)
    df_floors = df_floors.sort_values("sort_key", ascending=False)

    st.write(f"**{sp_asset}** 층별 입주 현황")

    for _, floor_row in df_floors.iterrows():
        floor_name = floor_row["floor"]
        exclusive = floor_row["exclusive_area"] * mult
        bank_area = floor_row.get("bank_area", 0.0)
        if pd.isna(bank_area):
            bank_area = 0.0
        bank_area *= mult

        # Find tenants on this floor
        floor_leases = df_leases_sp[df_leases_sp["floor"] == floor_name].copy()
        floor_leases["contract_area"] = floor_leases["contract_area"] * mult

        blocks_html = ""

        # Bank block
        if bank_area > 0:
            flex_val = max(0.1, bank_area)
            blocks_html += f"<div title='은행/지점&#10;면적: {bank_area:.1f} {unit_sp}' style='flex: {flex_val}; background-color: #005EB8; color: white; padding: 10px; margin: 2px; border-radius: 4px; text-align: center; min-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'><b>은행/지점</b><br>{bank_area:.1f}</div>"

        leased_total = 0.0
        for _, l_row in floor_leases.iterrows():
            comp = l_row["company_name"]
            area = (
                float(l_row["contract_area"])
                if not pd.isna(l_row["contract_area"])
                else 0.0
            )
            leased_total += area

            if "은행" in comp or "SC" in comp.upper() or "BANK" in comp.upper():
                bg_color = "#005EB8"  # SC Blue
                text_color = "white"
            else:
                bg_color = "#00A546"  # SC Green
                text_color = "white"

            if area > 0:
                flex_val = max(0.1, area)
                blocks_html += f"<div title='임차사: {comp}&#10;면적: {area:.1f} {unit_sp}' style='flex: {flex_val}; background-color: {bg_color}; color: {text_color}; padding: 10px; margin: 2px; border-radius: 4px; text-align: center; min-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'><b>{comp}</b><br>{area:.1f}</div>"

        vacant = float(exclusive) - float(bank_area) - leased_total
        if pd.isna(vacant):
            vacant = 0.0

        if vacant > 0.1:
            flex_val = max(0.1, vacant)
            blocks_html += f"<div title='공실&#10;면적: {vacant:.1f} {unit_sp}' style='flex: {flex_val}; background-color: #9ca3af; color: white; padding: 10px; margin: 2px; border-radius: 4px; text-align: center; min-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'><b>공실</b><br>{vacant:.1f}</div>"

        if blocks_html == "":
            # 면적이 0이거나 데이터가 없는 층 (RF 등)
            blocks_html = f"<div title='면적 0 / 데이터 없음' style='flex: 1; background-color: #e5e7eb; color: #6b7280; padding: 10px; margin: 2px; border-radius: 4px; text-align: center; min-width: 50px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'><b>0</b></div>"

        row_html = f"""
        <div style="display: flex; align-items: stretch; margin-bottom: 5px; border: 1px solid #e5e7eb; padding: 5px; background-color: #f9fafb; border-radius: 4px;">
            <div style="width: 80px; display: flex; align-items: center; justify-content: center; font-weight: bold; background-color: #f3f4f6; margin-right: 10px; border-radius: 4px;">
                {floor_name}
            </div>
            <div style="display: flex; flex: 1;">
                {blocks_html}
            </div>
        </div>
        """
        st.markdown(row_html, unsafe_allow_html=True)

else:
    st.info("등록된 자산 정보가 없습니다.")


# ==========================================
# Tab 2: 자산별 임대정보 관리
# ==========================================
