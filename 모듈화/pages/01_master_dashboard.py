import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("🌐 마스터 대시보드 (Executive Summary)")
import plotly.express as px
import numpy as np

df_assets_md = fetch_data("SELECT * FROM Asset_Area")
df_leases_md = fetch_data("SELECT * FROM Lease_Contracts WHERE status = 'ACTIVE'")

if df_assets_md.empty:
    st.warning("등록된 자산 정보가 없습니다.")
else:
    # [1단: 직관적 핵심 지표 (KPIs)]
    total_assets = df_assets_md["asset_name"].nunique()
    total_exclusive_area = df_assets_md["exclusive_area"].sum()
    total_bank_area = df_assets_md["bank_area"].sum() if "bank_area" in df_assets_md.columns else 0
        
    today_md = datetime.now()
        
    if not df_leases_md.empty:
        df_leases_md["start_date"] = pd.to_datetime(df_leases_md["start_date"])
        df_leases_md["end_date"] = pd.to_datetime(df_leases_md["end_date"])
        active_leases = df_leases_md[
            (df_leases_md["start_date"] <= today_md)
            & (df_leases_md["end_date"] >= today_md)
        ].copy()
    else:
        active_leases = pd.DataFrame()
            
    total_active_area = active_leases["contract_exclusive_area"].sum() if not active_leases.empty else 0
        
    # 1. 통합 관리 자산 및 임대율
    # 임대율 = (활성 임대 면적 + 은행 사용 면적) / 전체 전용 면적 * 100
    total_occupied = total_active_area + total_bank_area
    occupancy_rate = (total_occupied / total_exclusive_area * 100) if total_exclusive_area > 0 else 0
        
    # 2. 전체 임차사 및 활성 계약 수
    unique_companies = active_leases["company_name"].nunique() if not active_leases.empty else 0
    total_contracts = len(active_leases)
        
    # 3. 당월 총 청구 수익
    if not active_leases.empty:
        def get_krw_val(row, col):
            val = row[col] if pd.notnull(row[col]) else 0
            if row.get("currency", "KRW") == "USD":
                return val * CURRENCY_RATES["USD_TO_KRW"]
            return val

        active_leases["rent_krw"] = active_leases.apply(lambda r: get_krw_val(r, "monthly_rent"), axis=1)
        active_leases["maint_krw"] = active_leases.apply(lambda r: get_krw_val(r, "monthly_maintenance_fee"), axis=1)
        monthly_revenue = active_leases["rent_krw"].sum() + active_leases["maint_krw"].sum()
    else:
        monthly_revenue = 0

    # 4. 통합 공실 면적
    vacant_area = max(0, total_exclusive_area - total_occupied)

    st.markdown("### 📊 포트폴리오 핵심 지표 (Executive KPIs)")
    c1, c2, c3, c4 = st.columns(4, vertical_alignment="bottom")
    c1.metric(
        "통합 관리 자산 및 임대율",
        f"{total_assets}개",
        f"임대율: {occupancy_rate:.1f}%",
    )
    c2.metric(
        "전체 임차사 및 활성 계약 수",
        f"{unique_companies}개 사",
        f"계약 {total_contracts}건",
    )
    mr_str = f"₩ {monthly_revenue/1000000:,.0f}백만" if monthly_revenue >= 1000000 else f"₩ {monthly_revenue:,.0f}"
    c3.metric(
        "당월 총 청구 수익",
        mr_str,
    )
    c4.metric(
        "통합 공실 면적",
        f"{vacant_area:,.1f} 평",
    )

    st.markdown("---")

    # [2단: 3대 핵심 시각화 차트]
    st.markdown("### 📈 통합 데이터 시각화 (Portfolio Analytics)")
    p1, p2 = st.columns(2, vertical_alignment="bottom")
        
    sc_palette = ["#005EB8", "#00A546", "#38BDF8", "#34D399", "#94A3B8"]

    with p1:
        with st.container(border=True):
            st.markdown("#### 포트폴리오 공간 점유 현황")
            pie_df = pd.DataFrame({
                "Category": ["은행/지점 사용 면적", "일반 테넌트 임대 면적", "공실 면적"],
                "Area": [total_bank_area, total_active_area, vacant_area]
            })
            pie_df = pie_df[pie_df["Area"] > 0]
            if not pie_df.empty:
                fig_pie = px.pie(
                    pie_df, 
                    names="Category", 
                    values="Area", 
                    hole=0.4,
                    color_discrete_sequence=sc_palette
                )
                fig_pie.update_layout(
                    margin=dict(l=0, r=0, t=30, b=0),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("데이터 없음")

    with p2:
        with st.container(border=True):
            st.markdown("#### 자산별 월별 임대료 수입 (당해)")
            if not active_leases.empty:
                current_year = today_md.year
                all_assets = active_leases["asset_name"].unique().tolist()
                
                # 월별 임대료 계산을 위해 전체 계약 데이터 로드
                df_all_leases_md = fetch_data("SELECT * FROM Lease_Contracts")
                
                monthly_data = []
                for month_num in range(1, 13):
                    for asset in all_assets:
                        asset_contracts = df_all_leases_md[df_all_leases_md["asset_name"] == asset]
                        groups = asset_contracts[["floor", "company_name"]].drop_duplicates()
                        total_rent = 0.0
                        for _, g in groups.iterrows():
                            r, _ = get_actual_monthly_rent_by_company(
                                df_all_leases_md, asset, g["floor"], g["company_name"],
                                current_year, month_num, ignore_rent_free=True
                            )
                            total_rent += r
                        monthly_data.append({
                            "월": f"{month_num}월",
                            "월_정렬": month_num,
                            "자산명": asset,
                            "임대료": round(total_rent)
                        })
                
                df_monthly = pd.DataFrame(monthly_data)
                if not df_monthly.empty and df_monthly["임대료"].sum() > 0:
                    df_monthly = df_monthly.sort_values("월_정렬")
                    fig_monthly = px.line(
                        df_monthly,
                        x="월",
                        y="임대료",
                        color="자산명",
                        markers=True,
                        color_discrete_sequence=sc_palette
                    )
                    fig_monthly.update_layout(
                        xaxis_title="",
                        yaxis_title="임대료 (원)",
                        margin=dict(l=0, r=0, t=30, b=0),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(showgrid=False, zeroline=False),
                        yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickformat=","),
                        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
                    )
                    fig_monthly.update_traces(line=dict(width=2.5))
                    st.plotly_chart(fig_monthly, use_container_width=True)
                else:
                    st.info("당해 임대료 데이터가 없습니다.")
            else:
                st.info("데이터 없음")
                    
    st.markdown("---")
        
    # [3단: 자산별 평단가 비교]
    with st.container(border=True):
        st.markdown("#### 자산별 평균 평단가 비교 (임대료 및 관리비)")
        if not active_leases.empty:
            valid_leases = active_leases[active_leases["contract_area"].astype(float) > 0].copy()
            valid_leases["rent_unit"] = valid_leases["rent_krw"] / valid_leases["contract_area"].astype(float)
            valid_leases["maint_unit"] = valid_leases["maint_krw"] / valid_leases["contract_area"].astype(float)
            df_unit = valid_leases.groupby("asset_name")[["rent_unit", "maint_unit"]].mean().reset_index()
                
            df_unit["total_unit"] = df_unit["rent_unit"] + df_unit["maint_unit"]
            df_unit = df_unit.sort_values(by="total_unit", ascending=False)
                
            df_melt = df_unit.melt(
                id_vars=["asset_name"], 
                value_vars=["rent_unit", "maint_unit"], 
                var_name="Type", 
                value_name="Unit_Price"
            )
            df_melt["Type"] = df_melt["Type"].replace({"rent_unit": "임대료", "maint_unit": "관리비"})
                
            fig_bar2 = px.bar(
                df_melt,
                x="asset_name",
                y="Unit_Price",
                color="Type",
                barmode="group",
                color_discrete_sequence=["#005EB8", "#34D399"]
            )
            fig_bar2.update_layout(
                xaxis_title="자산명",
                yaxis_title="평단가 (KRW)",
                margin=dict(l=0, r=0, t=30, b=0),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, zeroline=False),
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False),
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig_bar2.update_traces(texttemplate='₩ %{y:,.0f}', textposition='outside')
            st.plotly_chart(fig_bar2, use_container_width=True)
        else:
            st.info("데이터 없음")




# ==========================================
# Tab 0.5: 시장 동향 리서치
# ==========================================
