import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("📈 시장 동향 리서치 (한국부동산원 API 연동)")
st.markdown("한국부동산원 상업용부동산 임대동향조사 오픈 API를 연동하여 주요 상권의 임대료 및 공실률 추이를 분석합니다. *(현재는 UI 데모용 가상 데이터를 표출 중입니다)*")
    
market_df = fetch_market_research_data()
    
f1, f2, f3 = st.columns(3, vertical_alignment="bottom")
with f1:
    sel_regions = st.multiselect("📍 지역명(시/도)", options=market_df["지역명(시/도)"].unique(), default=["서울"])
with f2:
    sel_types = st.multiselect("🏢 자산 유형", options=market_df["자산 유형"].unique(), default=["오피스"])
with f3:
    latest_q = sorted(market_df["기준 분기"].unique())[-1]
    sel_quarters = st.multiselect("📅 기준 분기", options=market_df["기준 분기"].unique(), default=[latest_q])
        
filtered_mdf = market_df.copy()
if sel_regions:
    filtered_mdf = filtered_mdf[filtered_mdf["지역명(시/도)"].isin(sel_regions)]
if sel_types:
    filtered_mdf = filtered_mdf[filtered_mdf["자산 유형"].isin(sel_types)]
if sel_quarters:
    filtered_mdf = filtered_mdf[filtered_mdf["기준 분기"].isin(sel_quarters)]
        
st.markdown("---")
    
if not filtered_mdf.empty:
    agg_df = filtered_mdf.groupby("세부 상권명")[["평당 임대료", "공실률(%)"]].mean().reset_index()
    agg_df = agg_df.sort_values(by="평당 임대료", ascending=False)
        
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    with c1:
        with st.container(border=True):
            st.markdown("#### 상권별 평균 평당 임대료")
            fig_rent = px.bar(agg_df, x="세부 상권명", y="평당 임대료")
            fig_rent.update_traces(marker_color="#005EB8", texttemplate='₩ %{y:,.0f}', textposition='outside')
            fig_rent.update_layout(
                margin=dict(l=0, r=0, t=30, b=0),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, zeroline=False, title=""),
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False)
            )
            st.plotly_chart(fig_rent, use_container_width=True)
                
    with c2:
        with st.container(border=True):
            st.markdown("#### 상권별 평균 공실률 (%)")
            fig_vac = px.bar(agg_df, x="세부 상권명", y="공실률(%)")
            fig_vac.update_traces(marker_color="#00A546", texttemplate='%{y:.1f}%', textposition='outside')
            fig_vac.update_layout(
                margin=dict(l=0, r=0, t=30, b=0),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, zeroline=False, title=""),
                yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False)
            )
            st.plotly_chart(fig_vac, use_container_width=True)
                
    st.markdown("---")
    st.markdown("#### 📋 상세 데이터 테이블")
    format_dict = {
        "㎡당 임대료": "₩ {:,.0f}",
        "평당 임대료": "₩ {:,.0f}",
        "공실률(%)": "{:.1f}%"
    }
    display_styled_table(filtered_mdf, freeze_cols=1, format_dict=format_dict)
else:
    st.info("검색 조건에 일치하는 데이터가 없습니다.")


