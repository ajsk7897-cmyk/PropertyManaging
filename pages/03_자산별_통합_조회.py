import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *


st.header("자산별 면적 현황 조회")

df_asset = fetch_data("SELECT * FROM Asset_Area")

if not df_asset.empty:
    # Filter
    assets = df_asset["asset_name"].unique().tolist()
    selected_assets = st.multiselect(
        "🏢 자산명 필터 (미선택 시 전체 조회)", options=assets, default=[]
    )

    if selected_assets:
        df_asset = df_asset[df_asset["asset_name"].isin(selected_assets)]

    today_str = datetime.now().strftime("%Y-%m-%d")
    # 현재 활성화된 계약 면적 산출
    df_leases = fetch_data(
        f"SELECT asset_name, floor, contract_exclusive_area FROM Lease_Contracts WHERE start_date <= '{today_str}' AND end_date >= '{today_str}' AND status = 'ACTIVE'"
    )

    if not df_leases.empty:
        leased_area_df = (
            df_leases.groupby(["asset_name", "floor"])["contract_exclusive_area"]
            .sum()
            .reset_index()
        )
        leased_area_df.rename(
            columns={"contract_exclusive_area": "leased_area"}, inplace=True
        )
        display_df = pd.merge(
            df_asset, leased_area_df, on=["asset_name", "floor"], how="left"
        )
        display_df["leased_area"] = display_df["leased_area"].fillna(0.0)
    else:
        display_df = df_asset.copy()
        display_df["leased_area"] = 0.0

    # Ensure bank_area is available
    if "bank_area" not in display_df.columns:
        display_df["bank_area"] = 0.0

    display_df["vacant_area"] = (
        display_df["exclusive_area"]
        - display_df["bank_area"].fillna(0.0)
        - display_df["leased_area"].fillna(0.0)
    )
    display_df["occupancy_rate (%)"] = (
        (
            display_df["leased_area"]
            / display_df["total_area"].replace(0, float("nan"))
            * 100
        )
        .fillna(0)
        .round(2)
    )
    display_df = sort_df_by_asset_and_floor(display_df, "asset_name", "floor")

    # 1. 자산별 토탈 대시보드
    dashboard_df = (
        display_df.groupby("asset_name")
        .agg(
            {
                "total_area": "sum",
                "common_area": "sum",
                "exclusive_area": "sum",
                "bank_area": "sum",
                "leased_area": "sum",
                "vacant_area": "sum",
            }
        )
        .reset_index()
    )

    dashboard_df["occupancy_rate (%)"] = (
        (
            dashboard_df["leased_area"]
            / dashboard_df["total_area"].replace(0, float("nan"))
            * 100
        )
        .fillna(0)
        .round(2)
    )
    dashboard_df = sort_df_by_asset_and_floor(dashboard_df, "asset_name", "floor")

    total_row_dash = pd.DataFrame(
        [
            {
                "asset_name": "TOTAL",
                "total_area": dashboard_df["total_area"].sum(),
                "common_area": dashboard_df["common_area"].sum(),
                "exclusive_area": dashboard_df["exclusive_area"].sum(),
                "bank_area": dashboard_df["bank_area"].sum(),
                "leased_area": dashboard_df["leased_area"].sum(),
                "vacant_area": dashboard_df["vacant_area"].sum(),
            }
        ]
    )
    if total_row_dash["total_area"][0] > 0:
        total_row_dash["occupancy_rate (%)"] = round(
            (total_row_dash["leased_area"][0] / total_row_dash["total_area"][0])
            * 100,
            2,
        )
    else:
        total_row_dash["occupancy_rate (%)"] = 0.0

    dashboard_df = pd.concat([dashboard_df, total_row_dash], ignore_index=True)

    # Add Summary Row to details
    if not display_df.empty:
        summary = pd.DataFrame(
            [
                {
                    "asset_name": "TOTAL",
                    "floor": "-",
                    "exclusive_area": display_df["exclusive_area"].sum(),
                    "common_area": display_df["common_area"].sum(),
                    "total_area": display_df["total_area"].sum(),
                    "bank_area": display_df["bank_area"].sum(),
                    "leased_area": display_df["leased_area"].sum(),
                    "vacant_area": display_df["vacant_area"].sum(),
                }
            ]
        )
        if summary["total_area"][0] > 0:
            summary["occupancy_rate (%)"] = round(
                (summary["leased_area"][0] / summary["total_area"][0]) * 100, 2
            )
        else:
            summary["occupancy_rate (%)"] = 0.0

        display_df = pd.concat([display_df, summary], ignore_index=True)

    st.write("")
    unit_option = st.radio(
        "🔄 표출 면적 단위 선택",
        ["평", "㎡", "sqft"],
        horizontal=True,
        key="tab1_unit_radio",
    )

    # Dashboard conversion
    dashboard_df_conv = dashboard_df.copy()
    dashboard_df_conv.rename(
        columns={
            "asset_name": "자산명",
            "total_area": "전체면적",
            "common_area": "공용면적",
            "bank_area": "은행 및 지점 사용 면적",
            "exclusive_area": "전용면적",
            "leased_area": "테넌트 면적",
            "vacant_area": "공실면적",
            "occupancy_rate (%)": "임대율 (%)",
        },
        inplace=True,
    )

    dashboard_order = [
        "자산명",
        "전체면적",
        "공용면적",
        "전용면적",
        "은행 및 지점 사용 면적",
        "테넌트 면적",
        "공실면적",
        "임대율 (%)",
    ]
    dashboard_df_conv = dashboard_df_conv[dashboard_order]

    area_cols = [
        "전체면적",
        "공용면적",
        "전용면적",
        "은행 및 지점 사용 면적",
        "테넌트 면적",
        "공실면적",
    ]

    if unit_option == "㎡":
        for col in area_cols:
            dashboard_df_conv[col] = (dashboard_df_conv[col] * CURRENCY_RATES["PY_TO_SQM"]).round(2)
    elif unit_option == "sqft":
        for col in area_cols:
            dashboard_df_conv[col] = (dashboard_df_conv[col] * CURRENCY_RATES["PY_TO_SF"]).round(2)

    csv_dash = generate_formatted_excel(dashboard_df_conv)
    file_name_dash = f"asset_total_dashboard_{unit_option}.xlsx"

    col_dash1, col_dash2, col_dash3, col_dash4 = st.columns([2.5, 3.5, 2.5, 1.5], vertical_alignment="bottom")
    with col_dash1:
        st.markdown("### 📊 자산별 토탈 대시보드")
            
    with col_dash2:
        st.download_button(
            "📊 토탈 엑셀 다운로드",
            data=csv_dash,
            file_name=file_name_dash,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
            
    with col_dash3:
        to_email_dash = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key="email_tab1_dash")
            
    with col_dash4:
        if st.button("🚀 메일 발송", key="btn_email_tab1_dash", use_container_width=True):
            if to_email_dash:
                success, err = send_email_with_attachment(
                    to_email=to_email_dash,
                    subject="[PM/AM] 자산별 토탈 대시보드 리포트",
                    body="요청하신 자산별 토탈 대시보드 리포트 파일을 첨부하여 보내드립니다.",
                    file_bytes=csv_dash,
                    file_name=file_name_dash,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                if success:
                    st.toast("메일이 성공적으로 발송되었습니다!", icon="✅")
                else:
                    st.error(f"메일 발송 실패: {err}")
            else:
                st.warning("이메일 주소를 입력해주세요.")

    display_styled_table(
        center_styler(dashboard_df_conv).format(
            {c: "{:,.2f}" for c in area_cols + ["임대율 (%)"]}
        )
    )

    st.markdown("---")

    display_df_conv = display_df.copy()

    display_df_conv.rename(
        columns={
            "asset_name": "자산명",
            "floor": "해당층",
            "total_area": "전체면적",
            "common_area": "공용면적",
            "bank_area": "은행 및 지점 사용 면적",
            "exclusive_area": "전용면적",
            "leased_area": "테넌트 면적",
            "vacant_area": "공실면적",
            "occupancy_rate (%)": "임대율 (%)",
        },
        inplace=True,
    )

    # 열 배치 순서 변경: 전체면적 - 공용면적 - 전용면적 - 은행 및 지점 사용 면적 - 테넌트 면적 순
    desired_order = [
        "자산명",
        "해당층",
        "전체면적",
        "공용면적",
        "전용면적",
        "은행 및 지점 사용 면적",
        "테넌트 면적",
        "공실면적",
        "임대율 (%)",
    ]
    display_df_conv = display_df_conv[desired_order]

    area_cols = [
        "전체면적",
        "공용면적",
        "전용면적",
        "은행 및 지점 사용 면적",
        "테넌트 면적",
        "공실면적",
    ]

    if unit_option == "㎡":
        for col in area_cols:
            display_df_conv[col] = (display_df_conv[col] * CURRENCY_RATES["PY_TO_SQM"]).round(2)
    elif unit_option == "sqft":
        for col in area_cols:
            display_df_conv[col] = (display_df_conv[col] * CURRENCY_RATES["PY_TO_SF"]).round(2)

    csv = generate_formatted_excel(display_df_conv)
    file_name_1 = f"asset_area_status_{unit_option}.xlsx"

    col_a1, col_a2, col_a3, col_a4 = st.columns([2.5, 3.5, 2.5, 1.5], vertical_alignment="bottom")
    with col_a1:
        st.markdown("### 🏢 자산별 층별 상세 현황")
            
    with col_a2:
        st.download_button(
            "📊 현황 엑셀 다운로드",
            data=csv,
            file_name=file_name_1,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
            
    with col_a3:
        to_email_1 = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key="email_tab1")
            
    with col_a4:
        if st.button("🚀 메일 발송", key="btn_email_tab1", use_container_width=True):
            if to_email_1:
                success, err = send_email_with_attachment(
                    to_email=to_email_1,
                    subject="[PM/AM] 자산별 면적 현황 리포트",
                    body="요청하신 자산별 면적 현황 리포트 파일을 첨부하여 보내드립니다.",
                    file_bytes=csv,
                    file_name=file_name_1,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                if success:
                    st.toast("메일이 성공적으로 발송되었습니다!", icon="✅")
                else:
                    st.error(f"메일 발송 실패: {err}")
            else:
                st.warning("이메일 주소를 입력해주세요.")

    display_styled_table(
        center_styler(display_df_conv).format(
            {c: "{:,.2f}" for c in area_cols + ["임대율 (%)"]}
        )
    )
else:
    st.info(
        "등록된 자산 정보가 없습니다. '자산정보 업데이트' 탭에서 데이터를 입력해 주세요."
    )



# ==========================================
# Tab 1.5: 스태킹 플랜
# ==========================================
