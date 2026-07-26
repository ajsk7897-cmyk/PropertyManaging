import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("렌트롤 (Rent Roll) 관리 및 수동 조정")
st.markdown(
    "자동 산출된 금액 외에 예외적으로 조정이 필요한 달이 있다면 표의 금액을 직접 클릭하여 **수정 후 [저장]** 할 수 있습니다. 갱신/퇴점된 계약 이력도 해당 날짜에 맞춰 정상적으로 병합 표출됩니다."
)

# 렌트롤은 모든 상태의 계약 내역을 기반으로 산출
df_c = fetch_data("SELECT * FROM Lease_Contracts")

if not df_c.empty:
    col_f1, col_f2, col_y1 = st.columns(3, vertical_alignment="bottom")
    with col_f1:
        assets = df_c["asset_name"].unique().tolist()
        sel_assets = st.multiselect(
            "🏢 자산명 필터", options=assets, default=[], key="tab3_asset_filter"
        )
    with col_f2:
        companies = df_c["company_name"].unique().tolist()
        sel_companies = st.multiselect(
            "🏢 업체명 필터",
            options=companies,
            default=[],
            key="tab3_company_filter",
        )
    with col_y1:
        start_year = 2026
        selected_year = st.selectbox(
            "📅 조회 연도 선택",
            range(start_year, max(datetime.now().year, start_year) + 10),
            index=0,
        )

    if sel_assets:
        df_c = df_c[df_c["asset_name"].isin(sel_assets)]
    if sel_companies:
        df_c = df_c[df_c["company_name"].isin(sel_companies)]

    # Load Overrides
    df_overrides = fetch_data(
        f"SELECT * FROM RentRoll_Overrides WHERE year = {selected_year}"
    )
    overrides_dict = {}
    for _, ov in df_overrides.iterrows():
        overrides_dict[(ov["contract_id"], ov["floor"], ov["month"])] = (
            ov["over_rent"],
            ov["over_maint"],
        )

    records = []
    for _, row in df_c.iterrows():
        try:
            start = pd.to_datetime(row["start_date"])
            end = pd.to_datetime(row["end_date"])

            year_start = datetime(selected_year, 1, 1)
            year_end = datetime(selected_year, 12, 31)
            if start > year_end or end < year_start:
                continue

            rf_details = (
                json.loads(row["rent_free_details"])
                if row["rent_free_details"]
                else []
            )

            status_str = f"[{row['status']}] " if row["status"] != "ACTIVE" else ""

            # 5. 복층 계약 렌트롤 표기 방식 변경 (단일 행 통합)
            # 단일 층 표기로 통합, 비율 배분 제거
            floor_name_unified = row["floor"]
            floor_records = {
                floor_name_unified: {
                    "Contract_ID": row["contract_id"],
                    "자산명": row["asset_name"],
                    "층": floor_name_unified,
                    "업체명": status_str + row["company_name"],
                    "통화": (
                        row["currency"]
                        if "currency" in row and pd.notnull(row["currency"])
                        else "KRW"
                    ),
                }
            }

            start_month = 6 if selected_year == 2026 else 1
            for month in range(start_month, 13):
                month_str = f"{selected_year}-{month:02d}"
                _, last_day = calendar.monthrange(selected_year, month)
                curr_month_start = datetime(selected_year, month, 1)
                curr_month_end = datetime(selected_year, month, last_day)

                initial_rent = float(row.get("monthly_rent", 0.0) or 0.0)
                initial_maint = float(row.get("monthly_maintenance_fee", 0.0) or 0.0)
                rent_schedule_json = row.get("rent_schedule", None)
                currency = row.get("currency", "KRW")

                overlap_start = max(start, curr_month_start)
                overlap_end = min(end, curr_month_end)
                    
                rent_to_charge_total = 0.0
                maint_to_charge_total = 0.0

                if overlap_start <= overlap_end:
                    # 1. 렌트프리 여부 판별 (월 1회만 수행)
                    is_rf = month_str in (rf_details or [])
                        
                    # 2. 캐싱된 스케줄 배열 1회 로드
                    schedule = _parse_rent_schedule(rent_schedule_json)
                        
                    if not schedule:
                        overlap_days = (overlap_end - overlap_start).days + 1
                        rent_to_charge_total = 0.0 if is_rf else (initial_rent * overlap_days / last_day)
                        maint_to_charge_total = (initial_maint * overlap_days / last_day)
                    else:
                        # 3. 스케줄 구간(Chunk)별로 겹치는 일수만큼 연산 (Daily Loop 제거)
                        c_start = overlap_start
                        last_known_rent = initial_rent
                        last_known_maint = initial_maint
                            
                        while c_start <= overlap_end:
                            current_rent = last_known_rent
                            current_maint = last_known_maint
                            next_change_date = overlap_end + timedelta(days=1)
                                
                            for period in schedule:
                                s_date = pd.to_datetime(period["start_date"])
                                e_date = pd.to_datetime(period["end_date"])
                                    
                                if s_date <= c_start <= e_date:
                                    current_rent = float(period.get("rent", 0.0))
                                    current_maint = float(period.get("maint", 0.0))
                                    next_change_date = min(next_change_date, e_date + timedelta(days=1))
                                    break
                                elif c_start < s_date:
                                    next_change_date = min(next_change_date, s_date)
                                elif c_start > e_date:
                                    last_known_rent = float(period.get("rent", 0.0))
                                    last_known_maint = float(period.get("maint", 0.0))
                                
                            c_end = min(overlap_end, next_change_date - timedelta(days=1))
                            days = (c_end - c_start).days + 1
                                
                            rent_to_charge_total += 0.0 if is_rf else (current_rent * days / last_day)
                            maint_to_charge_total += (current_maint * days / last_day)
                                
                            c_start = c_end + timedelta(days=1)
                else:
                    rent_to_charge_total = 0
                    maint_to_charge_total = 0

                # 단일 행 표출이므로 비율 분배 로직(ratio) 삭제
                if (row["contract_id"], floor_name_unified, month) in overrides_dict:
                    o_rent, o_maint = overrides_dict[(row["contract_id"], floor_name_unified, month)]
                    floor_rent = o_rent
                    floor_maint = o_maint
                else:
                    floor_rent = rent_to_charge_total
                    floor_maint = maint_to_charge_total

                # 1. 원단위 유지 (이전의 10원 미만 절사 제거)
                if currency != "KRW":
                    floor_rent = round(floor_rent, 2)
                    floor_maint = round(floor_maint, 2)

                floor_records[floor_name_unified][f"{month}월 임대료"] = floor_rent
                floor_records[floor_name_unified][f"{month}월 관리비"] = floor_maint

            for fl, rec in floor_records.items():
                records.append(rec)

        except Exception as e:
            st.error(
                f"데이터 처리 중 오류 발생 (Contract ID: {row['contract_id']}): {e}"
            )

    if records:
        df_rr = pd.DataFrame(records)
        df_rr = sort_df_by_asset_and_floor(df_rr, "자산명", "층")

        df_rr_krw = df_rr[df_rr["통화"] == "KRW"].copy()
        df_rr_usd = df_rr[df_rr["통화"] == "USD"].copy()

        df_rr_with_sub, sub_indices = add_subtotal_rows(df_rr, "자산명")
        csv_rr = generate_formatted_excel(df_rr_with_sub, sub_indices)
        file_name_3 = f"rent_roll_{selected_year}_details.xlsx"

        col_r1, col_r2, col_r3, col_r4 = st.columns([2.5, 3.5, 2.5, 1.5], vertical_alignment="bottom")
        with col_r1:
            st.markdown(f"### {selected_year}년 렌트롤 상세 내역")
                
        with col_r2:
            st.download_button(
                "📥 통합 렌트롤 엑셀 다운로드",
                data=csv_rr,
                file_name=file_name_3,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
                
        with col_r3:
            to_email_3 = text_input_rr = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key="email_tab3")
                
        with col_r4:
            if st.button("🚀 메일 발송", key="btn_email_tab3", use_container_width=True):
                if to_email_3:
                    success, err = send_email_with_attachment(
                        to_email=to_email_3,
                        subject=f"[PM/AM] {selected_year}년 렌트롤 리포트",
                        body=f"요청하신 {selected_year}년 렌트롤 상세 내역을 첨부하여 보내드립니다.",
                        file_bytes=csv_rr,
                        file_name=file_name_3,
                        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    if success:
                        st.toast("메일이 성공적으로 발송되었습니다!", icon="✅")
                    else:
                        st.error(f"메일 발송 실패: {err}")
                else:
                    st.warning("이메일 주소를 입력해주세요.")

        view_mode = st.radio(
            "보기 모드 선택",
            ["👁️ 조회 모드 (완벽한 디자인 적용)", "📝 예외 숫자 편집 모드"],
            horizontal=True,
        )

        if view_mode == "👁️ 조회 모드 (완벽한 디자인 적용)":
            rr_css = """
            .custom-st-table.{uid} tr:nth-child(even) td:nth-child(odd):nth-child(n+5) { background-color: #e0f2fe !important; }
            .custom-st-table.{uid} tr:nth-child(odd) td:nth-child(odd):nth-child(n+5) { background-color: #f0f9ff !important; }
            .custom-st-table.{uid} th:nth-child(odd):nth-child(n+5) { background-color: #e0f2fe !important; }

            .custom-st-table.{uid} tr:nth-child(even) td:nth-child(even):nth-child(n+6) { background-color: #fef3c7 !important; }
            .custom-st-table.{uid} tr:nth-child(odd) td:nth-child(even):nth-child(n+6) { background-color: #fffbeb !important; }
            .custom-st-table.{uid} th:nth-child(even):nth-child(n+6) { background-color: #fef3c7 !important; }

            .custom-st-table.{uid} td:nth-child(even):nth-child(n+6), 
            .custom-st-table.{uid} th:nth-child(even):nth-child(n+6) {
                border-right: 2px solid #64748b !important;
            }
            """
            if not df_rr_krw.empty:
                st.markdown("#### 🇰🇷 KRW 렌트롤")
                format_dict_krw = {}
                start_m = 6 if selected_year == 2026 else 1

                def fmt_krw(x):
                    if pd.isna(x):
                        return ""
                    try:
                        val = float(x)
                        if abs(val) >= 1_000_000:
                            return f"₩ {val/1_000_000:,.1f}백만"
                        return f"₩ {val:,.0f}"
                    except:
                        return str(x)

                for m in range(start_m, 13):
                    format_dict_krw[f"{m}월 임대료"] = fmt_krw
                    format_dict_krw[f"{m}월 관리비"] = fmt_krw
                display_styled_table(
                    df_rr_krw.drop(columns=["Contract_ID"]),
                    freeze_cols=4,
                    format_dict=format_dict_krw,
                    custom_css=rr_css,
                )

            if not df_rr_usd.empty:
                st.markdown("#### 🇺🇸 USD 렌트롤")
                format_dict_usd = {}
                start_m = 6 if selected_year == 2026 else 1

                def fmt_usd(x):
                    if pd.isna(x):
                        return ""
                    try:
                        val = float(x)
                        if abs(val) >= 1_000_000:
                            return f"USD {val/1_000_000:,.2f}백만"
                        return f"USD {val:,.2f}"
                    except:
                        return str(x)

                for m in range(start_m, 13):
                    format_dict_usd[f"{m}월 임대료"] = fmt_usd
                    format_dict_usd[f"{m}월 관리비"] = fmt_usd
                display_styled_table(
                    df_rr_usd.drop(columns=["Contract_ID"]),
                    freeze_cols=4,
                    format_dict=format_dict_usd,
                    custom_css=rr_css,
                )
        else:
            st.info(
                "※ 숫자를 더블클릭하여 수정하신 후, 반드시 아래의 [저장] 버튼을 눌러주세요. 수정 모드에서는 스트림릿 기본 디자인만 지원됩니다."
            )
            disabled_cols = ["Contract_ID", "자산명", "층", "업체명", "통화"]
            col_config_base = {
                col: st.column_config.Column(disabled=True) for col in disabled_cols
            }

            edited_krw = None
            edited_usd = None

            if not df_rr_krw.empty:
                st.markdown("#### 🇰🇷 KRW 렌트롤")
                col_config_krw = col_config_base.copy()
                start_m = 6 if selected_year == 2026 else 1
                for month in range(start_m, 13):
                    col_r = f"{month}월 임대료"
                    col_m = f"{month}월 관리비"
                    df_rr_krw[col_r] = df_rr_krw[col_r].apply(
                        lambda x: f"{int(float(x)):,}"
                    )
                    df_rr_krw[col_m] = df_rr_krw[col_m].apply(
                        lambda x: f"{int(float(x)):,}"
                    )
                    col_config_krw[col_r] = st.column_config.TextColumn(
                        f"₩ {col_r}"
                    )
                    col_config_krw[col_m] = st.column_config.TextColumn(
                        f"₩ {col_m}"
                    )

                index_cols = ["Contract_ID", "자산명", "층", "업체명", "통화"]
                edited_krw = st.data_editor(
                    df_rr_krw,
                    use_container_width=True,
                    column_config=col_config_krw,
                    hide_index=True,
                    key=f"rr_editor_krw_{selected_year}",
                )

            if not df_rr_usd.empty:
                st.markdown("#### 🇺🇸 USD 렌트롤")
                col_config_usd = col_config_base.copy()
                start_m = 6 if selected_year == 2026 else 1
                for month in range(start_m, 13):
                    col_r = f"{month}월 임대료"
                    col_m = f"{month}월 관리비"
                    df_rr_usd[col_r] = df_rr_usd[col_r].apply(
                        lambda x: f"{float(x):,.2f}"
                    )
                    df_rr_usd[col_m] = df_rr_usd[col_m].apply(
                        lambda x: f"{float(x):,.2f}"
                    )
                    col_config_usd[col_r] = st.column_config.TextColumn(
                        f"USD {col_r}"
                    )
                    col_config_usd[col_m] = st.column_config.TextColumn(
                        f"USD {col_m}"
                    )

                index_cols = ["Contract_ID", "자산명", "층", "업체명", "통화"]
                edited_usd = st.data_editor(
                    df_rr_usd,
                    use_container_width=True,
                    column_config=col_config_usd,
                    hide_index=True,
                    key=f"rr_editor_usd_{selected_year}",
                )

            if st.button("💾 렌트롤 예외 수정사항 DB에 저장", type="primary"):
                db_conn = engine.raw_connection()
                c = db_conn.cursor()
                changes_made = 0

                def process_edited(df_edited, df_orig):
                    def safe_to_float(val):
                        if pd.isna(val) or val is None or str(val).strip() == "":
                            return 0.0
                        try:
                            import re
                            cleaned = re.sub(r"[^\d\.\-]", "", str(val))
                            if not cleaned: return 0.0
                            return float(cleaned)
                        except:
                            return 0.0

                    cnt = 0
                    if df_edited is None or df_edited.empty:
                        return cnt
                    for idx in df_edited.index:
                        start_m = 6 if selected_year == 2026 else 1
                        for month in range(start_m, 13):
                            rent_col = f"{month}월 임대료"
                            maint_col = f"{month}월 관리비"

                            new_rent = df_edited.loc[idx, rent_col]
                            new_maint = df_edited.loc[idx, maint_col]
                            old_rent = df_orig.loc[idx, rent_col]
                            old_maint = df_orig.loc[idx, maint_col]

                            if str(new_rent) != str(old_rent) or str(
                                new_maint
                            ) != str(old_maint):
                                cid = int(df_edited.loc[idx, "Contract_ID"])
                                fl = str(df_edited.loc[idx, "층"])
                                val_rent = safe_to_float(new_rent)
                                val_maint = safe_to_float(new_maint)
                                c.execute(
                                    """
                                    INSERT INTO RentRoll_Overrides (contract_id, floor, year, month, over_rent, over_maint)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                    ON CONFLICT(contract_id, floor, year, month)
                                    DO UPDATE SET over_rent=excluded.over_rent, over_maint=excluded.over_maint
                                """,
                                    (
                                        cid,
                                        fl,
                                        selected_year,
                                        month,
                                        val_rent,
                                        val_maint,
                                    ),
                                )
                                cnt += 1
                    return cnt

                changes_made += process_edited(edited_krw, df_rr_krw)
                changes_made += process_edited(edited_usd, df_rr_usd)

                if changes_made > 0:
                    db_conn.commit()
                    db_conn.close()
                    fetch_data.clear()
                    st.success(
                        f"✅ {changes_made}건의 렌트롤 예외 수정사항이 데이터베이스에 안전하게 저장되었습니다."
                    )
                else:
                    st.info("수정된 항목이 없습니다.")

else:
    st.info("해당 연도에 포함된 계약 정보가 없습니다.")


# ==========================================
# Tab: 임관리비 변동 현황
# ==========================================
