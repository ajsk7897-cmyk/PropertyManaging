import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("자산별 임대정보 관리")
st.info(
    "※ 현재 'ACTIVE' 상태인 활성 계약들만 노출됩니다. 퇴점(TERMINATED) 처리된 계약 및 과거 계약(갱신 완료로 인한 이전 기록)은 중복 표출 방지를 위해 숨김 처리됩니다."
)

# Only fetch ACTIVE contracts for current leasing info
df_contracts = fetch_data(
    "SELECT * FROM Lease_Contracts WHERE status = 'ACTIVE' OR status IS NULL"
)

if not df_contracts.empty:
    # Filters
    col_f1, col_f2 = st.columns(2, vertical_alignment="bottom")
    with col_f1:
        assets = df_contracts["asset_name"].unique().tolist()
        sel_assets = st.multiselect(
            "🏢 자산명 필터", options=assets, default=[], key="tab2_asset_filter"
        )
    with col_f2:
        companies = df_contracts["company_name"].unique().tolist()
        sel_companies = st.multiselect(
            "🏢 업체명 필터",
            options=companies,
            default=[],
            key="tab2_company_filter",
        )

    if sel_assets:
        df_contracts = df_contracts[df_contracts["asset_name"].isin(sel_assets)]
    if sel_companies:
        df_contracts = df_contracts[
            df_contracts["company_name"].isin(sel_companies)
        ]

    def calc_effective_rent(row):
        try:
            start = pd.to_datetime(row["start_date"])
            end = pd.to_datetime(row["end_date"])

            total_days = (end - start).days + 1
            total_months = total_days / 365 * 12

            if total_months <= 0:
                return 0
            rent = float(row["monthly_rent"])
            rf_months = float(row["total_rent_free_months"])
            return ((rent * total_months) - (rent * rf_months)) / total_months
        except:
            return 0

    df_contracts["effective_rent"] = df_contracts.apply(calc_effective_rent, axis=1)

    df_contracts["deposit_per_pyeong"] = (
        df_contracts["deposit"]
        / df_contracts["contract_area"].astype(float).replace(0, float("nan"))
    ).fillna(0)
    df_contracts["rent_per_pyeong"] = (
        df_contracts["monthly_rent"]
        / df_contracts["contract_area"].astype(float).replace(0, float("nan"))
    ).fillna(0)
    df_contracts["maintenance_per_pyeong"] = (
        df_contracts["monthly_maintenance_fee"]
        / df_contracts["contract_area"].astype(float).replace(0, float("nan"))
    ).fillna(0)

    display_cols = [
        "company_name",
        "asset_name",
        "floor",
        "start_date",
        "end_date",
        "contract_area",
        "contract_exclusive_area",
        "currency",
        "deposit",
        "deposit_per_pyeong",
        "monthly_rent",
        "rent_per_pyeong",
        "monthly_maintenance_fee",
        "maintenance_per_pyeong",
        "total_rent_free_months",
        "effective_rent",
        "remarks",
        "contract_id",
    ]

    df_display = df_contracts[display_cols].copy()

    # Ensure currency has a default
    df_display["currency"] = df_display["currency"].fillna("KRW")
    df_display = sort_df_by_asset_and_floor(df_display, "asset_name", "floor")

    rename_dict = {
        "contract_id": "계약ID",
        "asset_name": "자산명",
        "floor": "층",
        "company_name": "업체명",
        "start_date": "계약시작일",
        "end_date": "계약종료일",
        "contract_area": "계약면적(평)",
        "contract_exclusive_area": "전용면적(평)",
        "currency": "통화",
        "deposit": "보증금",
        "deposit_per_pyeong": "평당 보증금",
        "monthly_rent": "임대료",
        "rent_per_pyeong": "평당 임대료",
        "monthly_maintenance_fee": "관리비",
        "maintenance_per_pyeong": "평당 관리비",
        "total_rent_free_months": "렌트프리(개월)",
        "effective_rent": "실질 임대료",
        "remarks": "비고",
    }
    df_display.rename(columns=rename_dict, inplace=True)

    df_krw = df_display[df_display["통화"] == "KRW"].copy()
    df_usd = df_display[df_display["통화"] == "USD"].copy()

    csv2 = generate_formatted_excel(df_display)
    file_name_2 = "lease_contracts.csv"

    col_sum1, col_sum2, col_sum3, col_sum4 = st.columns([2.5, 3.5, 2.5, 1.5], vertical_alignment="bottom")
    with col_sum1:
        st.markdown("### 📊 자산 통합 Summary")
            
    with col_sum2:
        st.download_button(
            "📝 전체 통합 엑셀 다운로드",
            data=csv2,
            file_name=file_name_2,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
            
    with col_sum3:
        to_email_2 = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key="email_tab2")
            
    with col_sum4:
        if st.button("🚀 메일 발송", key="btn_email_tab2", use_container_width=True):
            if to_email_2:
                success, err = send_email_with_attachment(
                    to_email=to_email_2,
                    subject="[PM/AM] 통합 임대정보 리포트",
                    body="요청하신 통합 임대정보 리포트 파일을 첨부하여 보내드립니다.",
                    file_bytes=csv2,
                    file_name=file_name_2,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                if success:
                    st.toast("메일이 성공적으로 발송되었습니다!", icon="✅")
                else:
                    st.error(f"메일 발송 실패: {err}")
            else:
                st.warning("이메일 주소를 입력해주세요.")
    sum_krw_dep = df_krw["보증금"].sum() if not df_krw.empty else 0
    sum_krw_rent = df_krw["임대료"].sum() if not df_krw.empty else 0
    sum_krw_maint = df_krw["관리비"].sum() if not df_krw.empty else 0

    sum_usd_dep = df_usd["보증금"].sum() if not df_usd.empty else 0
    sum_usd_rent = df_usd["임대료"].sum() if not df_usd.empty else 0
    sum_usd_maint = df_usd["관리비"].sum() if not df_usd.empty else 0

    st.markdown(
        f"""
    <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
        <div style="background-color: white; padding: 1rem; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); flex: 1; text-align: center;">
            <p style="color: #64748b; font-size: 0.8rem; margin: 0; font-weight: 600;">총 보증금</p>
            <p style="color: #1e293b; font-size: 1.6rem; margin: 0; font-weight: 700;">₩ {sum_krw_dep:,.0f} <span style="font-size: 1rem; color: #94a3b8;">/ USD {sum_usd_dep:,.2f}</span></p>
        </div>
        <div style="background-color: white; padding: 1rem; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); flex: 1; text-align: center;">
            <p style="color: #64748b; font-size: 0.8rem; margin: 0; font-weight: 600;">총 임대료</p>
            <p style="color: #1e293b; font-size: 1.6rem; margin: 0; font-weight: 700;">₩ {sum_krw_rent:,.0f} <span style="font-size: 1rem; color: #94a3b8;">/ USD {sum_usd_rent:,.2f}</span></p>
        </div>
        <div style="background-color: white; padding: 1rem; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); flex: 1; text-align: center;">
            <p style="color: #64748b; font-size: 0.8rem; margin: 0; font-weight: 600;">총 관리비</p>
            <p style="color: #1e293b; font-size: 1.6rem; margin: 0; font-weight: 700;">₩ {sum_krw_maint:,.0f} <span style="font-size: 1rem; color: #94a3b8;">/ USD {sum_usd_maint:,.2f}</span></p>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    currency_cols_kor = [
        "보증금",
        "평당 보증금",
        "임대료",
        "평당 임대료",
        "관리비",
        "평당 관리비",
        "실질 임대료",
    ]

    if not df_krw.empty:
        st.markdown(
            "<p style='font-size: 0.9rem; font-weight: bold; margin-bottom: 0.5rem;'>계약 내역</p>",
            unsafe_allow_html=True,
        )
        display_styled_table(
            center_styler(df_krw).format(
                {
                    **{c: "₩ {:,.0f}" for c in currency_cols_kor},
                    "계약면적(평)": "{:,.2f}",
                    "전용면적(평)": "{:,.2f}",
                }
            )
        )

    if not df_usd.empty:
        st.markdown(
            "<p style='font-size: 0.9rem; font-weight: bold; margin-bottom: 0.5rem;'>USD 계약 내역</p>",
            unsafe_allow_html=True,
        )
        display_styled_table(
            center_styler(df_usd).format(
                {
                    **{c: "USD {:,.2f}" for c in currency_cols_kor},
                    "계약면적(평)": "{:,.2f}",
                    "전용면적(평)": "{:,.2f}",
                }
            )
        )

else:
    st.info("등록된 활성 계약 정보가 없습니다.")


# ==========================================
# Tab 3: 렌트롤 관리
# ==========================================

