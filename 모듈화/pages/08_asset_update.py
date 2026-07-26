import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils import *

st.header("자산정보 등록 및 업데이트")

st.markdown("### 1. CSV 일괄 업로드")

template_df = pd.DataFrame(
    columns=[
        "자산명",
        "해당층",
        "전체면적",
        "공용면적",
        "전용면적",
        "은행 및 지점 사용 면적",
    ]
)
template_csv = generate_formatted_excel(template_df)
st.download_button(
    "📝 빈 양식 다운로드 (CSV)",
    data=template_csv,
    file_name="asset_upload_template.csv",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.info(
    "※ 면적 단위는 **'평'**을 기준으로 입력하여 업로드해주세요. 기존에 동일한 자산/층이 있다면 덮어쓰기(업데이트) 됩니다."
)
uploaded_file = st.file_uploader(
    "작성된 자산정보 CSV 파일 선택", type=["csv", "xlsx", "xls"]
)
if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_upload = pd.read_csv(uploaded_file)
        else:
            df_upload = pd.read_excel(uploaded_file)

        st.markdown("#### 업로드된 데이터 미리보기")
        num_cols = [
            "전체면적",
            "공용면적",
            "전용면적",
            "은행 및 지점 사용 면적",
            "exclusive_area",
            "common_area",
            "total_area",
            "bank_area",
        ]

        for c in num_cols:
            if c in df_upload.columns:
                if pd.api.types.is_string_dtype(df_upload[c]):
                    df_upload[c] = df_upload[c].str.replace(",", "")
                df_upload[c] = pd.to_numeric(df_upload[c], errors="coerce").fillna(
                    0.0
                )

        display_styled_table(
            center_styler(df_upload).format(
                {c: "{:,.2f}" for c in num_cols if c in df_upload.columns}
            )
        )

        if st.button("✅ 데이터베이스에 최종 반영하기", type="primary"):
            df_to_process = df_upload.rename(
                columns={
                    "자산명": "asset_name",
                    "해당층": "floor",
                    "전체면적": "total_area",
                    "공용면적": "common_area",
                    "전용면적": "exclusive_area",
                    "은행 및 지점 사용 면적": "bank_area",
                }
            )

            db_conn = engine.raw_connection()
            c = db_conn.cursor()
            for _, row in df_to_process.iterrows():
                if all(
                    col in row
                    for col in [
                        "asset_name",
                        "floor",
                        "exclusive_area",
                        "common_area",
                        "total_area",
                    ]
                ):
                    bank_area = float(
                        row.get("bank_area", 0.0)
                        if not pd.isna(row.get("bank_area", 0.0))
                        else 0.0
                    )
                    c.execute(
                        """
                        INSERT INTO Asset_Area (asset_name, floor, exclusive_area, common_area, total_area, bank_area)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT(asset_name, floor) 
                        DO UPDATE SET 
                            exclusive_area=excluded.exclusive_area, 
                            common_area=excluded.common_area, 
                            total_area=excluded.total_area,
                            bank_area=excluded.bank_area
                    """,
                        (
                            row["asset_name"],
                            str(row["floor"]),
                            float(row["exclusive_area"]),
                            float(row["common_area"]),
                            float(row["total_area"]),
                            bank_area,
                        ),
                    )
            db_conn.commit()
            db_conn.close()
            fetch_data.clear()
            st.success("✅ 파일 업로드 및 DB 적용이 완료되었습니다.")
    except Exception as e:
        st.error(f"업로드 중 오류 발생: {e}")

st.markdown("---")
st.markdown("### 2. 자산 등록 및 수정")
asset_update_mode = st.radio("작업 선택", ["✨ 신규 자산 등록", "📝 기존 자산 수정"], horizontal=True)

sel_asset = ""
sel_floor = ""
default_exc = 0.0
default_com = 0.0
default_tot = 0.0
default_bank = 0.0

if asset_update_mode == "📝 기존 자산 수정":
    df_assets = fetch_data("SELECT * FROM Asset_Area")
    if df_assets.empty:
        st.warning("등록된 자산이 없습니다.")
    else:
        assets_list = df_assets["asset_name"].unique().tolist()
        sel_asset = st.selectbox("수정할 자산명 선택", assets_list)
            
        floors_list = df_assets[df_assets["asset_name"] == sel_asset]["floor"].unique().tolist()
        sel_floor = st.selectbox("수정할 층 선택", floors_list)
            
        if sel_asset and sel_floor:
            row = df_assets[(df_assets["asset_name"] == sel_asset) & (df_assets["floor"] == sel_floor)].iloc[0]
            default_exc = float(row.get("exclusive_area", 0.0))
            default_com = float(row.get("common_area", 0.0))
            default_tot = float(row.get("total_area", 0.0))
            default_bank = float(row.get("bank_area", 0.0))

with st.form("asset_manual_form"):
    col_m1, col_m2 = st.columns(2, vertical_alignment="bottom")
    with col_m1:
        if asset_update_mode == "✨ 신규 자산 등록":
            m_asset_name = st.text_input("자산명 (건물명)")
            m_floor = st.text_input("층수 (예: 1F, B1)")
        else:
            m_asset_name = st.text_input("자산명 (건물명)", value=sel_asset, disabled=True)
            m_floor = st.text_input("층수 (예: 1F, B1)", value=sel_floor, disabled=True)
                
    with col_m2:
        m_exclusive = st.number_input("전용 면적 (평)", min_value=0.0, step=1.0, value=default_exc)
        m_common = st.number_input("공용 면적 (평)", min_value=0.0, step=1.0, value=default_com)
        m_total = st.number_input("총 면적 (평)", min_value=0.0, step=1.0, value=default_tot)
        m_bank = st.number_input(
            "은행 및 지점 사용 면적 (평)", min_value=0.0, step=1.0, value=default_bank
        )

    submitted = st.form_submit_button("✅ 자산 정보 저장")
    if submitted:
        if m_asset_name and m_floor:
            try:
                db_conn = engine.raw_connection()
                c = db_conn.cursor()
                c.execute(
                    """
                    INSERT INTO Asset_Area (asset_name, floor, exclusive_area, common_area, total_area, bank_area)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(asset_name, floor) 
                    DO UPDATE SET 
                        exclusive_area=excluded.exclusive_area, 
                        common_area=excluded.common_area, 
                        total_area=excluded.total_area,
                        bank_area=excluded.bank_area
                """,
                    (
                        m_asset_name,
                        m_floor,
                        float(m_exclusive),
                        float(m_common),
                        float(m_total),
                        float(m_bank),
                    ),
                )
                db_conn.commit()
                db_conn.close()
                fetch_data.clear()
                st.success(
                    f"'{m_asset_name} {m_floor}' 정보가 성공적으로 저장되었습니다."
                )
            except Exception as e:
                st.error(f"저장 중 오류 발생: {e}")
        else:
            st.error("자산명과 층수는 필수 입력값입니다.")

st.markdown("---")
st.markdown("### 3. 등록된 자산 정보 삭제")
st.info("※ 등록된 자산 정보를 완전히 삭제합니다 (오기입 수정 용도).")

df_existing_assets = fetch_data("SELECT * FROM Asset_Area")
if not df_existing_assets.empty:
    asset_options = df_existing_assets.apply(
        lambda x: f"{x['asset_name']} - {x['floor']}", axis=1
    ).tolist()
    selected_assets_to_delete = st.multiselect(
        "삭제할 자산/층 다중 선택", asset_options
    )

    if st.button("🗑️ 선택 자산 일괄 삭제", type="primary"):
        if not selected_assets_to_delete:
            st.warning("삭제할 대상을 선택해주세요.")
        else:
            try:
                db_conn = engine.raw_connection()
                c = db_conn.cursor()
                for sel_item in selected_assets_to_delete:
                    sel_asset_name, sel_floor = sel_item.split(" - ", 1)
                    c.execute(
                        "DELETE FROM Asset_Area WHERE asset_name = %s AND floor = %s",
                        (sel_asset_name, sel_floor),
                    )
                db_conn.commit()
                db_conn.close()
                fetch_data.clear()
                st.success(
                    f"✅ {len(selected_assets_to_delete)}개의 자산 정보가 성공적으로 삭제되었습니다."
                )
                st.rerun()
            except Exception as e:
                st.error(f"삭제 중 오류 발생: {e}")
else:
    st.info("삭제할 자산 정보가 없습니다.")


# ==========================================
# Tab 5: 계약 업데이트
# ==========================================
