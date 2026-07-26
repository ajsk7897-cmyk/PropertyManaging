import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("계약 업데이트 이력 관리")
st.markdown("신규, 갱신, 퇴점 등 모든 계약 변동 이력을 월별로 조회합니다.")

# Check if History table has data
df_history = fetch_data("""
    SELECT h.history_id, h.action_month, h.action_date, h.action_type, 
           c.asset_name, c.floor, c.company_name, h.details 
    FROM Contract_History h
    LEFT JOIN Lease_Contracts c ON h.contract_id = c.contract_id
    ORDER BY h.history_id DESC
""")

if not df_history.empty:

    def format_details(val):
        if not val:
            return ""
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return " | ".join([f"{k}: {v}" for k, v in parsed.items()])
            return val
        except:
            return val

    df_history["details"] = df_history["details"].apply(format_details)

    df_history.rename(
        columns={
            "history_id": "이력ID",
            "action_month": "발생월",
            "action_date": "발생일",
            "action_type": "유형",
            "asset_name": "자산명",
            "floor": "층",
            "company_name": "업체명",
            "details": "상세내용",
        },
        inplace=True,
    )

    months = sorted(df_history["발생월"].unique().tolist(), reverse=True)
    types = sorted(df_history["유형"].unique().tolist())

    col_h1, col_h2 = st.columns(2, vertical_alignment="bottom")
    with col_h1:
        selected_month = st.selectbox("📅 이력 조회 연/월", ["전체보기"] + months)
    with col_h2:
        selected_types = st.multiselect(
            "🏷️ 이력 유형 필터 (전체보기 시 비워두세요)", options=types, default=[]
        )

    df_display_hist = df_history.copy()
    if selected_month != "전체보기":
        df_display_hist = df_display_hist[
            df_display_hist["발생월"] == selected_month
        ]
    if selected_types:
        df_display_hist = df_display_hist[
            df_display_hist["유형"].isin(selected_types)
        ]

    display_styled_table(center_styler(df_display_hist))

    renewals = df_display_hist[df_display_hist["유형"] == "갱신"]
    if not renewals.empty:
        st.markdown("---")
        st.markdown("#### 📄 갱신 이력 기안서류(Lease Renewal Proposal) 재출력")
        renewal_opts = renewals.apply(
            lambda x: f"[{x['이력ID']}] {x['자산명']} {x['층']} - {x['업체명']} ({x['발생일']})",
            axis=1,
        ).tolist()
        sel_hist_str = st.selectbox("다운로드할 갱신 이력 선택", renewal_opts)
        if sel_hist_str:
            hist_id = int(sel_hist_str.split("]")[0][1:])
            try:
                db_conn = engine.raw_connection()
                try:
                    c = db_conn.cursor()
                    new_contract_id = int(
                        c.execute(
                            "SELECT contract_id FROM Contract_History WHERE history_id = %s",
                            (hist_id,),
                        ).fetchone()[0]
                    )
                    details_str = c.execute(
                        "SELECT details FROM Contract_History WHERE history_id = %s",
                        (hist_id,),
                    ).fetchone()[0]
                    details_json = json.loads(details_str) if details_str else {}
                    old_contract_id = details_json.get("이전계약ID")
                finally:
                    db_conn.close()
                fetch_data.clear()

                if old_contract_id:
                    new_c = fetch_data(
                        f"SELECT * FROM Lease_Contracts WHERE contract_id = {new_contract_id}"
                    ).iloc[0]
                    old_c = fetch_data(
                        f"SELECT * FROM Lease_Contracts WHERE contract_id = {old_contract_id}"
                    ).iloc[0]

                    import proposal_generator
                    import importlib

                    importlib.reload(proposal_generator)
                    from proposal_generator import generate_renewal_proposal

                    old_data = {
                        "기존_총임대면적_평": old_c["contract_area"],
                        "기존_전용면적_평": old_c.get("contract_exclusive_area", 0),
                        "기존_월임대료": old_c["monthly_rent"],
                        "기존_월관리비": old_c["monthly_maintenance_fee"],
                        "기존_보증금": old_c["deposit"],
                        "기존_임대차기간": f"{old_c['start_date']} ~ {old_c['end_date']}",
                    }
                    new_data = {
                        "자산주소": new_c["asset_name"],
                        "GPMS_ID": f"C-{old_contract_id}",
                        "임차인명": new_c["company_name"],
                        "부동산사용목적": "업무시설",
                        "대리인명": "",
                        "임대층": new_c["floor"],
                        "신규_총임대면적_평": new_c["contract_area"],
                        "신규_전용면적_평": new_c.get("contract_exclusive_area", 0),
                        "갱신_보증금": new_c["deposit"],
                        "갱신_월임대료": new_c["monthly_rent"],
                        "갱신_월관리비": new_c["monthly_maintenance_fee"],
                        "갱신_임대차기간": f"{new_c['start_date']} ~ {new_c['end_date']}",
                        "갱신_임대시작일": new_c["start_date"],
                        "갱신_임대만료일": new_c["end_date"],
                        "보증금비고": new_c["remarks"] if new_c["remarks"] else "",
                        "임대료비고": "",
                        "관리비비고": "",
                        "기간비고": "",
                    }

                    c.execute(
                        "SELECT floor, contract_area, deposit, monthly_rent, monthly_maintenance_fee FROM Lease_Contracts WHERE asset_name = %s AND status = 'ACTIVE' AND contract_id != %s",
                        (new_c["asset_name"], new_contract_id),
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

                    file_bytes, filename = generate_renewal_proposal(
                        old_data, new_data, comps_data
                    )
                        
                    col_dl1, col_dl2, col_dl3 = st.columns([4, 4, 2], vertical_alignment="bottom")
                    with col_dl1:
                        st.download_button(
                            "📥 선택한 이력 기안파일 다운로드",
                            data=file_bytes,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                            
                    with col_dl2:
                        to_email_6 = st.text_input("이메일", label_visibility="collapsed", placeholder="수신자 이메일 주소 입력", key=f"email_tab6_{hist_id}")
                            
                    with col_dl3:
                        if st.button("🚀 메일 발송", key=f"btn_email_tab6_{hist_id}", use_container_width=True):
                            if to_email_6:
                                company_name = new_data.get('임차인명', '업체')
                                success, err = send_email_with_attachment(
                                    to_email=to_email_6,
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
                else:
                    st.warning(
                        "선택하신 이력에는 이전 계약 정보가 포함되어 있지 않습니다."
                    )
            except Exception as e:
                st.error(f"파일 생성 오류: {e}")
else:
    st.info("아직 등록된 업데이트 이력이 없습니다.")

