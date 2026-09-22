import psycopg2
import pandas as pd
import google.generativeai as genai
import streamlit as st
import json
from datetime import datetime

from utils import generate_annual_rent_roll

def get_db_schema():
    return '''
CREATE TABLE asset_area (
    asset_name TEXT,
    floor TEXT,
    exclusive_area REAL,
    common_area REAL,
    total_area REAL, 
    bank_area REAL DEFAULT 0.0,
    PRIMARY KEY (asset_name, floor)
);

CREATE TABLE lease_contracts (
    contract_id SERIAL PRIMARY KEY,
    asset_name TEXT,
    floor TEXT,
    company_name TEXT,
    contract_date DATE,
    start_date DATE,
    end_date DATE,
    contract_area REAL,
    deposit REAL,
    monthly_rent REAL,
    monthly_maintenance_fee REAL,
    total_rent_free_months INTEGER,
    rent_free_details TEXT,
    status TEXT DEFAULT 'ACTIVE',
    deposit_return_date DATE, 
    penalty_yn TEXT, 
    penalty_amount REAL, 
    parent_contract_id INTEGER, 
    currency TEXT DEFAULT 'KRW', 
    floor_details TEXT,
    escalation_cycle_years INTEGER, 
    rent_inc_rate REAL, 
    maint_inc_rate REAL, 
    contract_exclusive_area REAL,
    remarks TEXT, 
    rent_schedule TEXT
);
'''

def get_db_connection():
    try:
        db_url = st.secrets.get("DATABASE_URL")
        if db_url:
            from urllib.parse import unquote
            db_url = unquote(db_url)
            return psycopg2.connect(db_url)
    except:
        pass
    
    try:
        conn_info = st.secrets["connections"]["postgresql"]
        return psycopg2.connect(
            host=conn_info["host"],
            port=conn_info["port"],
            database=conn_info["database"],
            user=conn_info["username"],
            password=conn_info["password"]
        )
    except:
        pass
    
    import os
    secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
            content = f.read()
            for line in content.split("\n"):
                if line.startswith("DATABASE_URL"):
                    from urllib.parse import unquote
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    url = unquote(url)
                    return psycopg2.connect(url)
    
    raise Exception("데이터베이스 연결 정보를 찾을 수 없습니다.")

def execute_sql_query(sql_query: str) -> str:
    '''
    데이터베이스에 원시 SQL(SELECT)을 실행하여 결과를 마크다운 표 문자열로 반환합니다.
    단순한 계약 내역, 자산 면적, 보증금 등을 조회할 때 사용하세요.
    연간 임대료 수입이나 렌트롤을 계산할 때는 이 도구 대신 get_annual_rent_roll을 사용하세요.
    '''
    if not sql_query.strip().upper().startswith("SELECT"):
        return "오류: SELECT 쿼리만 실행할 수 있습니다."
    
    import re
    sql_query = re.sub(r'"([^"]+)"', lambda m: m.group(1).lower(), sql_query)
    sql_query = sql_query.replace('Lease_Contracts', "lease_contracts")
    sql_query = sql_query.replace('Asset_Area', "asset_area")
    sql_query = sql_query.replace('RentRoll_Overrides', "rentroll_overrides")
    sql_query = sql_query.replace('Contract_History', "contract_history")
    
    asset_name_aliases = {
        r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
        r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
        r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
        r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
        r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
    }
    for pattern, real_key in asset_name_aliases.items():
        sql_query = re.sub(rf"'%([^']*)({pattern})([^']*)%'", f"'%{real_key}%'", sql_query, flags=re.IGNORECASE)
        sql_query = re.sub(rf"'({pattern})'", f"'%{real_key}%'", sql_query, flags=re.IGNORECASE)

    try:
        conn = get_db_connection()
        df = pd.read_sql_query(sql_query, conn)
        conn.close()
        return df.to_markdown() if not df.empty else "조회된 데이터가 없습니다."
    except Exception as e:
        return f"쿼리 실행 오류: {e}"

def get_annual_rent_roll(year: int, asset_name: str = "") -> str:
    '''
    렌트프리, 중도 입퇴점, 수동 예외조정, 임대료 정기 인상 등을 모두 완벽히 반영하여 계산된
    특정 연도의 렌트롤(월별 임대료 및 관리비 수입 총합) 데이터를 조회합니다.
    사용자가 '연간 임대료 수입', '연간 관리비 수입', '특정 연도의 수입' 등을 물어볼 때 반드시 이 도구를 사용하세요.
    asset_name은 영문자산명(HQ, Busan 등) 혹은 빈 문자열을 입력하세요.
    '''
    try:
        sel_assets = None
        if asset_name and asset_name.strip() != "":
            import re
            asset_name_aliases = {
                r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
                r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
                r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
                r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
                r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
            }
            mapped_asset = asset_name
            for pattern, real_key in asset_name_aliases.items():
                if re.search(pattern, asset_name, re.IGNORECASE):
                    mapped_asset = real_key
                    break
            sel_assets = [mapped_asset]
            
        df_rr, _ = generate_annual_rent_roll(year, sel_assets=sel_assets)
        if df_rr.empty:
            return f"{year}년에 해당하는 렌트롤 데이터가 없습니다."
            
        start_m = 6 if year == 2026 else 1
        
        total_rent = 0
        total_maint = 0
        summary_str = f"[{year}년 렌트롤 수입 요약 (자산: {asset_name or '전체'})]\n"
        for m in range(start_m, 13):
            r_col = f"{m}월 임대료"
            m_col = f"{m}월 관리비"
            m_rent = df_rr[r_col].sum() if r_col in df_rr.columns else 0
            m_maint = df_rr[m_col].sum() if m_col in df_rr.columns else 0
            total_rent += m_rent
            total_maint += m_maint
            summary_str += f"- {m}월: 임대료 {m_rent:,.0f}원, 관리비 {m_maint:,.0f}원\n"
            
        summary_str += f"\n=> 총 연간 임대료 수입: {total_rent:,.0f}원\n"
        summary_str += f"=> 총 연간 관리비 수입: {total_maint:,.0f}원\n"
        
        return summary_str
    except Exception as e:
        return f"렌트롤 계산 중 오류 발생: {e}"

def get_gemini_api_key():
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    import os
    try:
        secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            with open(secrets_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY"):
                        return line.split("=")[1].strip().strip('"').strip("'")
    except:
        pass
    return None

def generate_chat_response(user_message, chat_history):
    api_key = get_gemini_api_key()
    if not api_key:
        return "GEMINI API 키가 설정되지 않았습니다. 앱을 재시작해 주세요."
    
    import os
    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GOOGLE_API_KEY"] = api_key
    
    genai.configure(api_key=api_key)
    
    system_instruction = f'''
당신은 친절하고 전문적인 부동산 자산관리 어시스턴트입니다.
사용자의 질문을 파악하여 적절한 도구(Tool)를 사용해 답변하세요.

1. DB 조회가 필요한 단순 계약 정보(특정 업체의 보증금, 월세 등)는 `execute_sql_query` 도구를 사용하세요.
(DB 스키마:\n{get_db_schema()})
2. 연간 임대료 수입, 월별 임대료 수입, 렌트롤 총합 등 복잡한 렌트롤 계산이 필요한 경우 절대 DB 쿼리로 직접 계산하려 하지 말고, 반드시 `get_annual_rent_roll` 도구를 사용하세요.
3. 도구를 호출하여 조회된 결과를 바탕으로 사용자에게 친절하고 이해하기 쉬운 한글 자연어로 최종 답변을 작성하세요. 표나 요약 기호를 적절히 활용하세요.
'''

    model = genai.GenerativeModel(
        model_name='gemini-3.5-flash-lite',
        tools=[execute_sql_query, get_annual_rent_roll],
        system_instruction=system_instruction
    )

    try:
        chat = model.start_chat(enable_automatic_function_calling=True)
        prompt = f"[최근 대화 요약]\n{chat_history}\n\n[사용자 질문]\n{user_message}"
        response = chat.send_message(prompt)
        return response.text
    except Exception as e:
        return f"죄송합니다. 답변을 생성하는 도중 오류가 발생했습니다: {e}"
