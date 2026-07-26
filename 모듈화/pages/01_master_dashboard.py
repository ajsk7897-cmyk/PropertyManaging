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
            st.markdown("#### 연도별 만기 도래 면적 (향후 5년)")
            if not active_leases.empty:
                current_year = today_md.year
                active_leases["end_year"] = active_leases["end_date"].dt.year
                df_exp = active_leases[
                    (active_leases["end_year"] >= current_year) & 
                    (active_leases["end_year"] <= current_year + 5)
                ]
                if not df_exp.empty:
                    df_exp_grp = df_exp.groupby("end_year")["contract_area"].sum().reset_index()
                    df_exp_grp["end_year"] = df_exp_grp["end_year"].astype(str)
                    fig_exp = px.bar(
                        df_exp_grp,
                        x="end_year",
                        y="contract_area",
                        color_discrete_sequence=[sc_palette[0]]
                    )
                    fig_exp.update_layout(
                        xaxis_title="만기 연도",
                        yaxis_title="만기 도래 면적(평)",
                        margin=dict(l=0, r=0, t=30, b=0),
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(showgrid=False, zeroline=False),
                        yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False),
                        showlegend=False
                    )
                    fig_exp.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                    st.plotly_chart(fig_exp, use_container_width=True)
                else:
                    st.info("향후 5년 내 만기 도래 계약 없음")
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
