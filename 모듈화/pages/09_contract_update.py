import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("계약 등록 및 갱신/퇴점 처리")

update_mode = st.radio(
    "작업 유형 선택",
    [
        "✨ 신규 계약",
        "🔄 계약 갱신",
        "📝 기존 계약 수정",
        "❌ 퇴점",
        "🗑️ 계약 완전 삭제",
        "📥 일괄 등록 (CSV/Excel)",
    ],
    horizontal=True,
)

df_asset_options = fetch_data("SELECT DISTINCT asset_name, floor FROM Asset_Area")
asset_list = (
    df_asset_options["asset_name"].unique().tolist()
    if not df_asset_options.empty
    else []
)

if not asset_list:
    st.warning(
        "⚠️ 등록된 자산 정보가 없습니다. '자산정보 업데이트' 탭에서 자산을 먼저 등록해주세요."
    )
    st.stop()

# Active contracts only for Renew/Terminate
df_contracts_active = fetch_data(
    "SELECT * FROM Lease_Contracts WHERE status = 'ACTIVE' OR status IS NULL"
)
target_contract_id = None

# ------------------
# 1) 갱신/퇴점/삭제 모드일 경우 기존 계약 선택
# ------------------
if update_mode in ["🔄 계약 갱신", "📝 기존 계약 수정", "❌ 퇴점", "🗑️ 계약 완전 삭제"]:
    if update_mode == "🗑️ 계약 완전 삭제":
        df_for_selection = fetch_data("SELECT * FROM Lease_Contracts")
        warning_msg = "등록된 계약이 없습니다."
    else:
        df_for_selection = df_contracts_active
        warning_msg = "등록된 유효한(ACTIVE) 기존 계약이 없습니다."

    if df_for_selection.empty:
        st.warning(warning_msg)
        st.stop()

    options = df_for_selection.apply(
        lambda x: f"[{x['contract_id']}] {x['asset_name']} {x['floor']} - {x['company_name']} ({x['status']})",
        axis=1,
    ).tolist()

    if update_mode == "🗑️ 계약 완전 삭제":
        selected_contract_strs = st.multiselect(
            "삭제할 기존 계약 다중 선택", options
        )
        target_contract_ids = [
            int(sel.split("]")[0][1:]) for sel in selected_contract_strs
        ]
    else:
        selected_contract_str = st.selectbox(
            "적용할 기존 계약 선택", 
            options, 
            index=None, 
            placeholder="계약을 검색하거나 선택하세요"
        )
            
        if not selected_contract_str:
            st.info("👆 검색 창을 클릭하여 타이핑하거나 목록에서 계약을 선택해주세요.")
            st.stop()
                
        target_contract_id = int(selected_contract_str.split("]")[0][1:])
        row_sel = df_for_selection[
            df_for_selection["contract_id"] == target_contract_id
        ].iloc[0]

# ------------------
# 2) 퇴점 폼 렌더링
# ------------------
if update_mode == "❌ 퇴점":
    st.markdown("---")
    st.markdown("#### 퇴점 처리 정보 입력")
    term_type = st.radio("퇴점 유형", ["만기 종료", "조기 종료"])

    col_t1, col_t2 = st.columns(2, vertical_alignment="bottom")
    with col_t1:
        term_date_default = pd.to_datetime(row_sel["end_date"]).date()
        if term_type == "조기 종료":
            term_date_default = datetime.now().date()
        new_end_date = st.date_input("최종 계약 종료일", value=term_date_default)
        deposit_return_date = st.date_input(
            "보증금 반환일", value=term_date_default
        )
    with col_t2:
        penalty_yn = st.selectbox("위약벌 여부", ["N", "Y"])
        penalty_amount = 0
        if penalty_yn == "Y":
            penalty_amount = st.number_input(
                "위약벌(위약금) 청구 액수", min_value=0, step=1000000
            )

    if st.button(
        "❌ 선택 계약 퇴점 처리", type="primary", use_container_width=True
    ):
        if (
            new_end_date > pd.to_datetime(row_sel["end_date"]).date()
            and term_type == "조기 종료"
        ):
            st.error("조기 종료일은 기존 계약 종료일보다 늦을 수 없습니다.")
        else:
            try:
                db_conn = engine.raw_connection()
                c = db_conn.cursor()
                # 기존 계약 상태 터미네이트로 변경 및 종료일 단축
                c.execute(
                    """
                    UPDATE Lease_Contracts 
                    SET status = 'TERMINATED', end_date = %s, deposit_return_date = %s, penalty_yn = %s, penalty_amount = %s
                    WHERE contract_id = %s
                """,
                    (
                        new_end_date.strftime("%Y-%m-%d"),
                        deposit_return_date.strftime("%Y-%m-%d"),
                        penalty_yn,
                        float(penalty_amount),
                        target_contract_id,
                    ),
                )

                # 이력 관리 추가
                today_str = datetime.now().strftime("%Y-%m-%d")
                month_str = datetime.now().strftime("%Y-%m")
                details_json = json.dumps(
                    {
                        "유형": term_type,
                        "종료일": new_end_date.strftime("%Y-%m-%d"),
                        "위약금": penalty_amount,
                    },
                    ensure_ascii=False,
                )
                c.execute(
                    """
                    INSERT INTO Contract_History (contract_id, action_type, action_date, action_month, details)
                    VALUES (%s, %s, %s, %s, %s)
                """,
                    (
                        target_contract_id,
                        "퇴점",
                        today_str,
                        month_str,
                        details_json,
                    ),
                )

                db_conn.commit()
                db_conn.close()
                fetch_data.clear()
                st.success(
                    "✅ 퇴점 처리가 완료되었습니다. 렌트롤은 조기종료년도까지만 반영되고 이후 목록에서 제외됩니다."
                )
            except Exception as e:
                st.error(f"오류 발생: {e}")

# ------------------
# 3) 삭제 폼 렌더링
# ------------------
elif update_mode == "🗑️ 계약 완전 삭제":
    st.markdown("---")
    st.markdown("#### 계약 일괄 완전 삭제")
    if not target_contract_ids:
        st.info("삭제할 계약을 1개 이상 선택해주세요.")
    else:
        st.warning(
            f"⚠️ 선택하신 {len(target_contract_ids)}개의 계약과 관련된 모든 이력 및 렌트롤 수동 조정 데이터가 완전히 삭제됩니다."
        )

        if st.button(
            "🗑️ 영구 일괄 삭제 진행", type="primary", use_container_width=True
        ):
            try:
                db_conn = engine.raw_connection()
                c = db_conn.cursor()
                for t_id in target_contract_ids:
                    c.execute(
                        "DELETE FROM Lease_Contracts WHERE contract_id = %s",
                        (t_id,),
                    )
                    c.execute(
                        "DELETE FROM RentRoll_Overrides WHERE contract_id = %s",
                        (t_id,),
                    )
                    c.execute(
                        "DELETE FROM Contract_History WHERE contract_id = %s",
                        (t_id,),
                    )
                db_conn.commit()
                db_conn.close()
                fetch_data.clear()
                st.success(
                    f"✅ {len(target_contract_ids)}개의 계약이 데이터베이스에서 완전히 삭제되었습니다."
                )
                st.rerun()
            except Exception as e:
                st.error(f"삭제 중 오류 발생: {e}")

# ------------------
# 4) 신규/갱신 폼 렌더링
# ------------------
elif update_mode in ["✨ 신규 계약", "🔄 계약 갱신", "📝 기존 계약 수정"]:
    default_vals = {
        "asset_name": asset_list[0],
        "floor": "",
        "company": "",
        "area": 0.0,
        "exclusive_area": 0.0,
        "c_date": datetime.now().date(),
        "s_date": datetime.now().date(),
        "e_date": datetime.now().date().replace(year=datetime.now().year + 2),
        "deposit": 0,
        "rent": 0,
        "maint": 0,
        "rf_details": [],
        "floor_details": {},
        "remarks": ""
    }

    if update_mode in ["🔄 계약 갱신", "📝 기존 계약 수정"]:
        default_vals["asset_name"] = row_sel["asset_name"]
        default_vals["floor"] = row_sel["floor"]
        default_vals["company"] = row_sel["company_name"]
        default_vals["area"] = (
            float(row_sel["contract_area"])
            if pd.notnull(row_sel["contract_area"])
            else 0.0
        )
        default_vals["exclusive_area"] = (
            float(row_sel.get("contract_exclusive_area", 0.0))
            if pd.notnull(row_sel.get("contract_exclusive_area", 0.0))
            else 0.0
        )
            
        old_start = pd.to_datetime(row_sel["start_date"]).date()
        old_end = pd.to_datetime(row_sel["end_date"]).date()
            
        if update_mode == "🔄 계약 갱신":
            default_vals["s_date"] = old_end + timedelta(days=1)
            default_vals["e_date"] = default_vals["s_date"].replace(
                year=default_vals["s_date"].year + 2
            )
        else: # 📝 기존 계약 수정
            if "contract_date" in row_sel and pd.notnull(row_sel["contract_date"]):
                default_vals["c_date"] = pd.to_datetime(row_sel["contract_date"]).date()
            else:
                default_vals["c_date"] = old_start
            default_vals["s_date"] = old_start
            default_vals["e_date"] = old_end
                
            if row_sel.get("rent_free_details"):
                try:
                    default_vals["rf_details"] = json.loads(row_sel["rent_free_details"])
                except:
                    pass
            if row_sel.get("floor_details"):
                try:
                    default_vals["floor_details"] = json.loads(row_sel["floor_details"])
                except:
                    pass
            if row_sel.get("rent_schedule"):
                default_vals["rent_schedule"] = row_sel["rent_schedule"]
            if row_sel.get("remarks"):
                default_vals["remarks"] = row_sel["remarks"]

        default_vals["deposit"] = int(row_sel["deposit"])
        default_vals["rent"] = int(row_sel["monthly_rent"])
        default_vals["maint"] = int(row_sel["monthly_maintenance_fee"])

    key_suffix = f"_{target_contract_id}" if update_mode != "✨ 신규 계약" else "_new"

    with st.container():
        st.markdown(
            "<div style='background-color: white; padding: 2rem; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);'>",
            unsafe_allow_html=True,
        )

        st.markdown("#### 기본 계약 형태")
        col_t1, col_t2 = st.columns(2, vertical_alignment="bottom")
        with col_t1:
            idx_ct = 0
            if update_mode in ["🔄 계약 갱신", "📝 기존 계약 수정"]:
                if len(default_vals.get("floor_details", {})) > 1 or "," in default_vals["floor"]:
                    idx_ct = 1
            contract_type = st.radio(
                "계약 형태", ["단층 계약", "복층 계약"], index=idx_ct, horizontal=True
            )
        with col_t2:
            idx_curr = 0
            if update_mode in ["🔄 계약 갱신", "📝 기존 계약 수정"]:
                if "USD" in str(row_sel.get("currency", "")):
                    idx_curr = 1
            currency = st.radio("계약 통화", ["KRW", "USD"], index=idx_curr, horizontal=True)

        st.markdown("---")
        col_a, col_b = st.columns(2, vertical_alignment="bottom")
        with col_a:
            try:
                asset_idx = asset_list.index(default_vals["asset_name"])
            except:
                asset_idx = 0

            if update_mode == "🔄 계약 갱신":
                asset_name = default_vals["asset_name"]
                st.text_input(
                    "자산명 (갱신 시 고정)", value=asset_name, disabled=True
                )
            else:
                asset_name = st.selectbox(
                    "자산명 (기존 등록 자산)", asset_list, index=asset_idx
                )

        with col_b:
            floor_list = df_asset_options[
                df_asset_options["asset_name"] == asset_name
            ]["floor"].tolist()
            floor_list = sorted(floor_list, key=get_floor_sort_key, reverse=True)
            if contract_type == "단층 계약":
                if update_mode == "🔄 계약 갱신":
                    floor_val = default_vals["floor"]
                    st.text_input("층 (고정)", value=floor_val, disabled=True)
                    sel_floors = [floor_val]
                else:
                    try:
                        floor_idx = floor_list.index(default_vals["floor"])
                    except:
                        floor_idx = 0
                    if floor_list:
                        floor_val = st.selectbox(
                            "해당 층", floor_list, index=floor_idx
                        )
                    else:
                        floor_val = st.selectbox("해당 층", ["없음"])
                    sel_floors = [floor_val] if floor_val != "없음" else []
            else:
                if update_mode == "🔄 계약 갱신":
                    st.info("복층 갱신 시 기존 층 정보를 재선택해주세요.")
                def_floors = []
                if update_mode == "📝 기존 계약 수정" and default_vals.get("floor_details"):
                    def_floors = [f for f in default_vals["floor_details"].keys() if f in floor_list]
                sel_floors = st.multiselect("해당 층 다중 선택", floor_list, default=def_floors)

        st.markdown("---")
        st.markdown("#### 업체 및 면적 정보")
        col_c1, col_c2 = st.columns(2, vertical_alignment="bottom")
        with col_c1:
            company_name = st.text_input(
                "🏢 업체명 (임차인)", value=default_vals["company"]
            )

        floor_areas = {}
        with col_c2:
            if contract_type == "단층 계약":
                col_f1, col_f2 = st.columns(2, vertical_alignment="bottom")
                with col_f1:
                    contract_area = st.number_input(
                        "📐 계약 총면적 (평)",
                        min_value=0.0,
                        step=1.0,
                        value=default_vals["area"],
                    )
                with col_f2:
                    contract_exclusive_area = st.number_input(
                        "📐 전용면적 (평)",
                        min_value=0.0,
                        step=1.0,
                        value=default_vals["exclusive_area"],
                    )
                if sel_floors:
                    floor_areas[sel_floors[0]] = {
                        "area": contract_area,
                        "exclusive_area": contract_exclusive_area,
                    }
            else:
                st.markdown("📐 **층별 계약 면적 (평)**")
                contract_area = 0.0
                contract_exclusive_area = 0.0
                for fl in sel_floors:
                    def_fl_area = 0.0
                    def_fl_exc = 0.0
                    if update_mode == "📝 기존 계약 수정" and default_vals.get("floor_details"):
                        if fl in default_vals["floor_details"]:
                            def_fl_area = float(default_vals["floor_details"][fl].get("area", 0.0))
                            def_fl_exc = float(default_vals["floor_details"][fl].get("exclusive_area", 0.0))
                    col_f1, col_f2 = st.columns(2, vertical_alignment="bottom")
                    with col_f1:
                        fl_area = st.number_input(
                            f"{fl} 총면적",
                            min_value=0.0,
                            step=1.0,
                            value=def_fl_area,
                            key=f"area_{fl}",
                        )
                    with col_f2:
                        fl_exc_area = st.number_input(
                            f"{fl} 전용면적",
                            min_value=0.0,
                            step=1.0,
                            value=def_fl_exc,
                            key=f"exc_area_{fl}",
                        )
                    floor_areas[fl] = {
                        "area": fl_area,
                        "exclusive_area": fl_exc_area,
                    }
                    contract_area += fl_area
                    contract_exclusive_area += fl_exc_area
                st.info(
                    f"총 면적 합계: {contract_area} 평 / 전용면적 합계: {contract_exclusive_area} 평"
                )

        st.markdown("---")
        col_d1, col_d2, col_d3 = st.columns(3, vertical_alignment="bottom")
        with col_d1:
            contract_date = st.date_input(
                "📝 새 계약 체결일", value=default_vals["c_date"]
            )
        with col_d2:
            start_date = st.date_input(
                "🟢 새 임대 시작일", value=default_vals["s_date"]
            )
        with col_d3:
            end_date = st.date_input(
                "🔴 새 임대 종료일", value=default_vals["e_date"]
            )

        st.markdown("---")
        st.markdown("#### 💳 임대 조건 (계약 전체 총액)")
        col_f1, col_f2, col_f3 = st.columns(3, vertical_alignment="bottom")
        with col_f1:
            dep_str = st.text_input(
                "보증금 (총액)", value=f"{int(default_vals['deposit']):,}"
            )
            deposit = (
                int(dep_str.replace(",", ""))
                if dep_str.replace(",", "").isdigit()
                else 0
            )
        with col_f2:
            rent_str = st.text_input(
                "월 임대료 (총액)", value=f"{int(default_vals['rent']):,}"
            )
            monthly_rent = (
                int(rent_str.replace(",", ""))
                if rent_str.replace(",", "").isdigit()
                else 0
            )
        with col_f3:
            maint_str = st.text_input(
                "월 관리비 (총액)", value=f"{int(default_vals['maint']):,}"
            )
            monthly_maintenance_fee = (
                int(maint_str.replace(",", ""))
                if maint_str.replace(",", "").isdigit()
                else 0
            )

        st.markdown("#### 📈 기간별 스케줄 (Rent Schedule)")
        st.info("해당 계약의 임대료 및 관리비 변동 스케줄을 입력하세요. 최초에는 전체 기간에 대한 단일 스케줄이 생성됩니다.")
            
        default_schedule_json = default_vals.get("rent_schedule", "")
        schedule_list = []
        if default_schedule_json:
            try:
                schedule_list = json.loads(default_schedule_json)
            except:
                pass
        if not schedule_list:
            schedule_list = [
                {
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "rent": monthly_rent,
                    "maint": monthly_maintenance_fee
                }
            ]
            
        df_schedule = pd.DataFrame(schedule_list)
        edited_schedule_df = st.data_editor(
            df_schedule,
            num_rows="dynamic",
            use_container_width=True,
            key=f"rent_schedule_editor{key_suffix}"
        )
            
        # 입력 데이터 정제 로직 (날짜 8자리 입력 허용 및 빈 숫자 0 처리)
        for col in ["start_date", "end_date"]:
            if col in edited_schedule_df.columns:
                edited_schedule_df[col] = pd.to_datetime(edited_schedule_df[col].astype(str), errors='coerce').dt.strftime("%Y-%m-%d").fillna("")
        for col in ["rent", "maint"]:
            if col in edited_schedule_df.columns:
                edited_schedule_df[col] = pd.to_numeric(edited_schedule_df[col], errors='coerce').fillna(0.0)

        rent_schedule_json = edited_schedule_df.to_json(orient="records", force_ascii=False)
            
        escalation_cycle_years = 0
        rent_inc_rate = 0.0
        maint_inc_rate = 0.0

        st.markdown("---")
        st.markdown("#### 🎁 새로운 렌트프리 설정")
        available_months = get_months_between(start_date, end_date)
        valid_default_rf = [
            m for m in default_vals["rf_details"] if m in available_months
        ]
        selected_rf_months = st.multiselect(
            "렌트프리 적용 월 선택",
            options=available_months,
            default=valid_default_rf,
            key=f"rf_months{key_suffix}"
        )
        total_rf_months = len(selected_rf_months)

        st.markdown("---")
        st.markdown("#### ✍️ 비고 사항")
        remarks = st.text_area("특약 및 비고 사항을 입력하세요.", value=default_vals.get("remarks", ""), key=f"remarks{key_suffix}")

        st.markdown("---")
        send_email = st.checkbox(
            "저장 완료 시 담당자에게 엑셀 보고서 발송", value=True
        )

        st.markdown("</div>", unsafe_allow_html=True)
        st.write("")

        if update_mode == "🔄 계약 갱신":
            try:
                import proposal_generator
                import importlib

                importlib.reload(proposal_generator)
                from proposal_generator import generate_renewal_proposal

                old_data = {
                    "기존_총임대면적_평": row_sel["contract_area"],
                    "기존_전용면적_평": row_sel.get("contract_exclusive_area", 0),
                    "기존_월임대료": row_sel["monthly_rent"],
                    "기존_월관리비": row_sel["monthly_maintenance_fee"],
                    "기존_보증금": row_sel["deposit"],
                    "기존_임대차기간": f"{row_sel['start_date']} ~ {row_sel['end_date']}",
                }
                new_data = {
                    "자산주소": asset_name,
                    "GPMS_ID": f"C-{target_contract_id}",
                    "임차인명": company_name,
                    "부동산사용목적": "업무시설",
                    "대리인명": "",
                    "임대층": ", ".join(sel_floors) if sel_floors else "",
                    "신규_총임대면적_평": contract_area,
                    "신규_전용면적_평": contract_exclusive_area,
                    "갱신_보증금": deposit,
                    "갱신_월임대료": monthly_rent,
                    "갱신_월관리비": monthly_maintenance_fee,
                    "갱신_임대차기간": f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
                    "갱신_임대시작일": start_date.strftime("%Y-%m-%d"),
                    "갱신_임대만료일": end_date.strftime("%Y-%m-%d"),
                    "보증금비고": remarks,
                    "임대료비고": "",
                    "관리비비고": "",
                    "기간비고": "",
                }

                db_conn = engine.raw_connection()
                try:
                    c = db_conn.cursor()
                    c.execute(
                        "SELECT floor, contract_area, deposit, monthly_rent, monthly_maintenance_fee FROM Lease_Contracts WHERE asset_name = %s AND status = 'ACTIVE' AND contract_id != %s",
                        (asset_name, target_contract_id),
                    )
                    comps_data = [
                        {
                            "floor": r[0],
                            "contract_area": r[1],
                            "deposit": r[2],
                            "monthly_rent": r[3],
                            "monthly_maintenance_fee": r[4],
                        }
                        for r in c.fetchall()
                    ]
                finally:
                    db_conn.close()

                file_bytes, filename = generate_renewal_proposal(
                    old_data, new_data, comps_data
                )
                    
                col_dl1, col_dl2, col_dl3 = st.columns([4, 4, 2], vertical_alignment="bottom")
                with col_dl1:
                    st.download_button(
                        "📄 갱신 기안서류 다운로드",
                        data=file_bytes,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                with col_dl2:
                    to_email_renewal = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key="email_renewal_entry")
                with col_dl3:
                    if st.button("🚀 메일 발송", key="btn_email_renewal_entry", use_container_width=True):
                        if to_email_renewal:
                            success, err = send_email_with_attachment(
                                to_email=to_email_renewal,
                                subject=f"[PM/AM] {company_name} 갱신 기안서류",
                                body=f"요청하신 {company_name}의 갱신 기안서류(Excel)를 첨부하여 보내드립니다.",
                                file_bytes=file_bytes,
                                file_name=filename,
                                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                            if success:
                                st.toast("메일이 성공적으로 발송되었습니다!", icon="✅")
                            else:
                                st.error(f"메일 발송 실패: {err}")
                        else:
                            st.warning("이메일 주소를 입력해주세요.")
            except Exception as e:
                st.warning(f"기안서류 생성 로딩 중 오류 (템플릿 확인 필요): {e}")

        if st.button(
            "✅ "
            + (
                "신규 계약 등록 완료"
                if update_mode == "✨ 신규 계약"
                else "갱신 정보 저장 및 반영"
            ),
            use_container_width=True,
        ):
            if not asset_name or not company_name or not sel_floors:
                st.error("자산명, 층, 업체명을 모두 올바르게 입력해주세요.")
            elif start_date > end_date:
                st.error("종료일은 시작일보다 이후여야 합니다.")
            elif contract_area < 0:
                st.error("계약 면적은 0 이상이어야 합니다.")
            else:
                # [UI 방어 로직] 계약 기간 중복 검증
                from 모듈화.utils import check_contract_overlap
                overlap_found = False
                exclude_id = None
                if update_mode not in ["✨ 신규 계약", "🔄 계약 갱신"]:
                    exclude_id = target_contract_id
                    
                for fl in sel_floors:
                    if check_contract_overlap(asset_name, fl, company_name, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), exclude_contract_id=exclude_id):
                        overlap_found = True
                        break
                        
                if overlap_found:
                    st.error("⚠️ 해당 업체(임차인)의 기존 계약과 기간이 겹칩니다. 기존 계약의 종료일을 앞당긴 후 다시 시도해 주세요.")
                    st.stop()

                try:
                    db_conn = engine.raw_connection()
                    c = db_conn.cursor()
                    rf_details_json = json.dumps(selected_rf_months)
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    month_str = datetime.now().strftime("%Y-%m")

                    floor_details_dict = {}
                    for fl, fl_info in floor_areas.items():
                        if isinstance(fl_info, dict):
                            fl_area = fl_info["area"]
                            fl_exc_area = fl_info["exclusive_area"]
                        else:
                            fl_area = fl_info
                            fl_exc_area = 0.0
                        floor_details_dict[fl] = {
                            "area": fl_area,
                            "exclusive_area": fl_exc_area,
                            "ratio": (
                                fl_area / contract_area if contract_area > 0 else 0
                            ),
                        }
                    floor_details_json = json.dumps(floor_details_dict)

                    contract_months = len(get_months_between(start_date, end_date))
                    period_str = f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} ({contract_months}개월)"
                    history_details = {
                        "계약기간": period_str,
                        "통화": currency,
                        "보증금": f"{int(deposit):,}",
                        "임대료": f"{int(monthly_rent):,}",
                        "관리비": f"{int(monthly_maintenance_fee):,}",
                    }

                    floor_str = ", ".join(sel_floors)

                    if update_mode == "✨ 신규 계약":
                        c.execute(
                            """
                            INSERT INTO Lease_Contracts (
                                asset_name, floor, company_name, contract_date, start_date, end_date,
                                contract_area, contract_exclusive_area, deposit, monthly_rent, monthly_maintenance_fee,
                                total_rent_free_months, rent_free_details, status,
                                currency, floor_details, escalation_cycle_years, rent_inc_rate, maint_inc_rate, rent_schedule, remarks
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s, %s)
                        """,
                            (
                                asset_name,
                                floor_str,
                                company_name,
                                contract_date.strftime("%Y-%m-%d"),
                                start_date.strftime("%Y-%m-%d"),
                                end_date.strftime("%Y-%m-%d"),
                                float(contract_area),
                                float(contract_exclusive_area),
                                float(deposit),
                                float(monthly_rent),
                                float(monthly_maintenance_fee),
                                total_rf_months,
                                rf_details_json,
                                currency,
                                floor_details_json,
                                escalation_cycle_years,
                                rent_inc_rate,
                                maint_inc_rate,
                                rent_schedule_json,
                                remarks,
                            ),
                        )
                        new_contract_id = c.lastrowid

                        c.execute(
                            """
                            INSERT INTO Contract_History (contract_id, action_type, action_date, action_month, details)
                            VALUES (%s, '신규', %s, %s, %s)
                        """,
                            (
                                new_contract_id,
                                today_str,
                                month_str,
                                json.dumps(history_details, ensure_ascii=False),
                            ),
                        )

                        db_conn.commit()
                        db_conn.close()
                        fetch_data.clear()
                        st.success(
                            f"🎉 '{company_name}' 신규 계약이 등록되었습니다."
                        )

                        if send_email:
                            try:
                                wb = load_workbook("report_template.xlsx")
                                ws = wb.active
                                ws["B3"] = company_name
                                ws["B4"] = asset_name
                                ws["B5"] = floor_str
                                ws["B6"] = start_date.strftime("%Y-%m-%d")
                                ws["B7"] = end_date.strftime("%Y-%m-%d")
                                ws["B8"] = deposit
                                ws["B9"] = monthly_rent
                                report_filename = f"report_{company_name}.xlsx"
                                wb.save(report_filename)

                                if "email" in st.secrets:
                                    msg = EmailMessage()
                                    msg["Subject"] = (
                                        f"[PM/AM] 신규 계약 체결 알림: {company_name}"
                                    )
                                    msg["From"] = st.secrets["email"]["user"]
                                    msg["To"] = st.secrets["email"]["receiver"]
                                    msg.set_content(
                                        f"신규 계약이 등록되었습니다.\n자산명: {asset_name}\n업체명: {company_name}"
                                    )

                                    with open(report_filename, "rb") as fa:
                                        msg.add_attachment(
                                            fa.read(),
                                            maintype="application",
                                            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            filename=report_filename,
                                        )

                                    with smtplib.SMTP_SSL(
                                        "smtp.gmail.com", 465
                                    ) as smtp:
                                        smtp.login(
                                            st.secrets["email"]["user"],
                                            st.secrets["email"]["password"],
                                        )
                                        smtp.send_message(msg)
                                    st.success(
                                        "📧 담당자에게 이메일 보고서가 발송되었습니다."
                                    )
                                else:
                                    st.warning(
                                        "⚠️ .streamlit/secrets.toml 에 이메일 설정이 없어 메일 발송이 생략되었습니다."
                                    )
                            except Exception as email_err:
                                st.warning(f"⚠️ 메일 발송 실패: {email_err}")

                    elif update_mode == "🔄 계약 갱신":
                        adjusted_old_end = start_date - timedelta(days=1)
                        c.execute(
                            """
                            UPDATE Lease_Contracts 
                            SET status = 'RENEWED', end_date = %s
                            WHERE contract_id = %s
                        """,
                            (
                                adjusted_old_end.strftime("%Y-%m-%d"),
                                target_contract_id,
                            ),
                        )

                        c.execute(
                            """
                            INSERT INTO Lease_Contracts (
                                asset_name, floor, company_name, contract_date, start_date, end_date,
                                contract_area, contract_exclusive_area, deposit, monthly_rent, monthly_maintenance_fee,
                                total_rent_free_months, rent_free_details, status, parent_contract_id,
                                currency, floor_details, escalation_cycle_years, rent_inc_rate, maint_inc_rate, rent_schedule, remarks
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                            (
                                asset_name,
                                floor_str,
                                company_name,
                                contract_date.strftime("%Y-%m-%d"),
                                start_date.strftime("%Y-%m-%d"),
                                end_date.strftime("%Y-%m-%d"),
                                float(contract_area),
                                float(contract_exclusive_area),
                                float(deposit),
                                float(monthly_rent),
                                float(monthly_maintenance_fee),
                                total_rf_months,
                                rf_details_json,
                                target_contract_id,
                                currency,
                                floor_details_json,
                                escalation_cycle_years,
                                rent_inc_rate,
                                maint_inc_rate,
                                rent_schedule_json,
                                remarks,
                            ),
                        )
                        new_contract_id = c.lastrowid

                        history_details["이전계약ID"] = target_contract_id
                        c.execute(
                            """
                            INSERT INTO Contract_History (contract_id, action_type, action_date, action_month, details)
                            VALUES (%s, '갱신', %s, %s, %s)
                        """,
                            (
                                new_contract_id,
                                today_str,
                                month_str,
                                json.dumps(history_details, ensure_ascii=False),
                            ),
                        )

                        db_conn.commit()
                        db_conn.close()
                        fetch_data.clear()
                        st.success(
                            f"🎉 '{company_name}' 계약이 성공적으로 갱신(버전 분리) 처리되었습니다."
                        )
                            
                    elif update_mode == "📝 기존 계약 수정":
                        c.execute(
                            """
                            UPDATE Lease_Contracts SET
                                asset_name = %s, floor = %s, company_name = %s, contract_date = %s, start_date = %s, end_date = %s,
                                contract_area = %s, contract_exclusive_area = %s, deposit = %s, monthly_rent = %s, monthly_maintenance_fee = %s,
                                total_rent_free_months = %s, rent_free_details = %s,
                                currency = %s, floor_details = %s, escalation_cycle_years = %s, rent_inc_rate = %s, maint_inc_rate = %s, rent_schedule = %s, remarks = %s
                            WHERE contract_id = %s
                        """,
                            (
                                asset_name,
                                floor_str,
                                company_name,
                                contract_date.strftime("%Y-%m-%d"),
                                start_date.strftime("%Y-%m-%d"),
                                end_date.strftime("%Y-%m-%d"),
                                float(contract_area),
                                float(contract_exclusive_area),
                                float(deposit),
                                float(monthly_rent),
                                float(monthly_maintenance_fee),
                                total_rf_months,
                                rf_details_json,
                                currency,
                                floor_details_json,
                                escalation_cycle_years,
                                rent_inc_rate,
                                maint_inc_rate,
                                rent_schedule_json,
                                remarks,
                                target_contract_id,
                            ),
                        )
                        c.execute(
                            """
                            INSERT INTO Contract_History (contract_id, action_type, action_date, action_month, details)
                            VALUES (%s, '정보수정', %s, %s, %s)
                        """,
                            (
                                target_contract_id,
                                today_str,
                                month_str,
                                json.dumps(history_details, ensure_ascii=False),
                            ),
                        )
                        db_conn.commit()
                        db_conn.close()
                        fetch_data.clear()
                        st.success(f"✏️ '{company_name}' 기존 계약 정보가 성공적으로 수정(UPDATE)되었습니다.")
                        st.rerun()

                except Exception as e:
                    st.error(f"데이터베이스 저장 오류: {e}")

# ------------------
# 5) 일괄 업로드 폼 렌더링
# ------------------
elif update_mode == "📥 일괄 등록 (CSV/Excel)":
    st.markdown("---")
    st.markdown("#### 계약 정보 일괄 업로드")

    template_cols = [
        "자산명",
        "업체명",
        "층",
        "통화",
        "계약 시작일",
        "계약 종료일",
        "전체면적",
        "전용면적",
        "보증금",
        "임대료",
        "관리비",
        "임대료 인상률",
        "관리비 인상률",
        "인상 주기",
        "기타 특약",
    ]
    example_data = {
        "자산명": "Pohang (작성예시)",
        "업체명": "포항시의사회",
        "층": "3F",
        "통화": "KRW",
        "계약 시작일": "2020-01-01",
        "계약 종료일": "2025-12-31",
        "전체면적": "39.9",
        "전용면적": "37.0",
        "보증금": "50000000",
        "임대료": "45430",
        "관리비": "0",
        "임대료 인상률": "5",
        "관리비 인상률": "0",
        "인상 주기": "1",
        "기타 특약": "매년 11월 1일 인상",
    }
    df_template = pd.DataFrame([example_data], columns=template_cols)
    csv_template = generate_formatted_excel(df_template)
    st.download_button(
        "📝 빈 양식 다운로드 (CSV)",
        data=csv_template,
        file_name="contract_upload_template.csv",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.info(
        "※ 다운로드한 양식에 맞춰 데이터를 입력하신 후 업로드해주세요. 모든 계약은 '단층'을 기준으로 임시 등록되며, 복층 등 특수 조건은 등록 후 개별 수정바랍니다."
    )

    uploaded_file = st.file_uploader(
        "작성된 계약정보 파일 선택", type=["csv", "xlsx", "xls"]
    )
    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                try:
                    df_up = pd.read_csv(uploaded_file)
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df_up = pd.read_csv(uploaded_file, encoding="cp949")
            else:
                df_up = pd.read_excel(uploaded_file)

            required_cols = ["자산명", "업체명", "계약 시작일"]
            missing_cols = [
                col for col in required_cols if col not in df_up.columns
            ]
            if missing_cols:
                st.error(
                    f"❌ 업로드된 파일에 다음 필수 컬럼이 누락되었습니다: {', '.join(missing_cols)}"
                )
                st.info(
                    "💡 다운로드한 빈 양식을 그대로 사용하여 첫 번째 행(헤더)이 변경되지 않도록 주의해주세요."
                )
            else:

                num_cols_up = [
                    "전체면적",
                    "전용면적",
                    "보증금",
                    "임대료",
                    "관리비",
                    "임대료 인상률",
                    "관리비 인상률",
                    "인상 주기",
                ]
                for c in num_cols_up:
                    if c in df_up.columns:
                        if pd.api.types.is_string_dtype(
                            df_up[c]
                        ) or pd.api.types.is_object_dtype(df_up[c]):
                            df_up[c] = (
                                df_up[c]
                                .astype(str)
                                .str.replace(r"[^\d\.\-]", "", regex=True)
                            )
                            df_up[c] = df_up[c].replace("", "0")
                        df_up[c] = pd.to_numeric(df_up[c], errors="coerce").fillna(
                            0.0
                        )

                st.markdown("#### 업로드된 데이터 미리보기")
                display_styled_table(
                    center_styler(df_up).format(
                        {
                            c: "{:,.2f}"
                            for c in ["전체면적", "전용면적"]
                            if c in df_up.columns
                        }
                    )
                )

                if st.button(
                    "✅ 데이터베이스에 최종 반영하기",
                    type="primary",
                    key="btn_bulk_contract_upload",
                ):
                    db_conn = engine.raw_connection()
                    c = db_conn.cursor()
                    inserted_count = 0
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    month_str = datetime.now().strftime("%Y-%m")

                    for _, row in df_up.iterrows():
                        if (
                            pd.isna(row.get("자산명"))
                            or pd.isna(row.get("업체명"))
                            or pd.isna(row.get("계약 시작일"))
                        ):
                            continue
                        if "(작성예시)" in str(row.get("자산명", "")):
                            continue

                        asset_name = str(row.get("자산명", "")).strip()
                        company_name = str(row.get("업체명", "")).strip()
                        floor_str = str(row.get("층", "")).strip()
                        currency = str(row.get("통화", "KRW")).strip()
                        if not currency or currency.lower() == "nan":
                            currency = "KRW"

                        try:
                            s_date = pd.to_datetime(
                                row.get("계약 시작일")
                            ).strftime("%Y-%m-%d")
                            e_date = pd.to_datetime(
                                row.get("계약 종료일")
                            ).strftime("%Y-%m-%d")
                        except:
                            st.warning(
                                f"'{company_name}' 계약의 날짜 형식이 잘못되어 건너뜁니다."
                            )
                            continue

                        def safe_float(val):
                            if pd.isna(val) or str(val).strip() == "":
                                return 0.0
                            if isinstance(val, str):
                                import re

                                val = re.sub(r"[^\d\.\-]", "", str(val))
                            try:
                                return float(val)
                            except:
                                return 0.0

                        c_area = safe_float(row.get("전체면적"))
                        e_area = safe_float(row.get("전용면적"))
                        dep = safe_float(row.get("보증금"))
                        rent = safe_float(row.get("임대료"))
                        maint = safe_float(row.get("관리비"))
                        r_inc = safe_float(row.get("임대료 인상률"))
                        m_inc = safe_float(row.get("관리비 인상률"))
                        esc_cycle = int(safe_float(row.get("인상 주기")))
                        remarks = (
                            str(row.get("기타 특약", ""))
                            if pd.notnull(row.get("기타 특약"))
                            else ""
                        )
                        if remarks.lower() == "nan":
                            remarks = ""

                        floor_details_dict = {
                            floor_str: {"area": c_area, "ratio": 1.0}
                        }
                        floor_details_json = json.dumps(
                            floor_details_dict, ensure_ascii=False
                        )

                        rent_schedule = [{"start_date": s_date, "end_date": e_date, "rent": rent, "maint": maint}]
                        rent_schedule_json = json.dumps(rent_schedule, ensure_ascii=False)

                        c.execute(
                            """
                            INSERT INTO Lease_Contracts (
                                asset_name, floor, company_name, contract_date, start_date, end_date,
                                contract_area, contract_exclusive_area, deposit, monthly_rent, monthly_maintenance_fee,
                                total_rent_free_months, rent_free_details, status,
                                currency, floor_details, escalation_cycle_years, rent_inc_rate, maint_inc_rate, rent_schedule, remarks
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s, %s, %s)
                        """,
                            (
                                asset_name,
                                floor_str,
                                company_name,
                                s_date,
                                s_date,
                                e_date,
                                c_area,
                                e_area,
                                dep,
                                rent,
                                maint,
                                0,
                                "[]",
                                currency,
                                floor_details_json,
                                esc_cycle,
                                r_inc,
                                m_inc,
                                rent_schedule_json,
                                remarks,
                            ),
                        )

                        new_id = c.lastrowid
                        history_details = {
                            "계약기간": f"{s_date} ~ {e_date}",
                            "통화": currency,
                            "보증금": f"{int(dep):,}",
                            "임대료": f"{int(rent):,}",
                            "관리비": f"{int(maint):,}",
                        }
                        c.execute(
                            """
                            INSERT INTO Contract_History (contract_id, action_type, action_date, action_month, details)
                            VALUES (%s, '신규(일괄등록)', %s, %s, %s)
                        """,
                            (
                                new_id,
                                today_str,
                                month_str,
                                json.dumps(history_details, ensure_ascii=False),
                            ),
                        )

                        inserted_count += 1

                    db_conn.commit()
                    db_conn.close()
                    fetch_data.clear()
                    if inserted_count > 0:
                        st.success(
                            f"✅ {inserted_count}건의 계약 정보 일괄 등록이 완료되었습니다."
                        )
                    else:
                        st.warning(
                            "등록된 데이터가 없습니다. 양식과 내용을 확인해주세요."
                        )
        except Exception as e:
            st.error(f"업로드 중 오류 발생: {e}")


# ==========================================
# Tab 6: 업데이트 이력 관리 (New Tab)
# ==========================================
