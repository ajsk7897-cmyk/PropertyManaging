import psycopg2
import pandas as pd
import google.generativeai as genai
import streamlit as st
import json
from datetime import datetime

def get_db_schema():
    return """
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
    rent_free_details TEXT,       -- JSON 배열 문자열. 예: '["2025-10","2025-11"]'. 특정 월의 렌트프리 여부를 확인하려면 rent_free_details LIKE '%2025-10%' 형태로 조회.
    status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE' 또는 'TERMINATED'
    deposit_return_date DATE, 
    penalty_yn TEXT, 
    penalty_amount REAL, 
    parent_contract_id INTEGER, 
    currency TEXT DEFAULT 'KRW', 
    floor_details TEXT,           -- JSON 문자열
    escalation_cycle_years INTEGER, 
    rent_inc_rate REAL, 
    maint_inc_rate REAL, 
    contract_exclusive_area REAL,
    remarks TEXT, 
    rent_schedule TEXT             -- JSON 배열. 기간별 임대료/관리비 변동 내역
);

CREATE TABLE rentroll_overrides (
    contract_id INTEGER,
    floor TEXT,
    year INTEGER,
    month INTEGER,
    over_rent REAL,
    over_maint REAL,
    PRIMARY KEY (contract_id, year, month)
);

CREATE TABLE contract_history (
    history_id SERIAL PRIMARY KEY,
    contract_id INTEGER,
    action_type TEXT,
    action_date DATE,
    action_month TEXT,
    details TEXT
);

-- 중요: 모든 테이블명과 컬럼명은 소문자입니다. 큰따옴표 없이 그대로 사용하세요.
-- 예시: SELECT * FROM lease_contracts WHERE asset_name = 'HQ빌딩';
"""

def get_db_connection():
    """PostgreSQL 연결 (앱의 실제 DB와 동일)"""
    try:
        db_url = st.secrets.get("DATABASE_URL")
        if db_url:
            # URL-encoded 문자 디코딩
            from urllib.parse import unquote
            db_url = unquote(db_url)
            return psycopg2.connect(db_url)
    except:
        pass
    
    # fallback: 개별 설정값 사용
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
    
    # 최후 fallback: secrets.toml 직접 파싱
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

def execute_query(sql_query):
    # Only allow SELECT
    if not sql_query.strip().upper().startswith("SELECT"):
        return "보안상의 이유로 SELECT 쿼리만 실행할 수 있습니다."
    
    try:
        conn = get_db_connection()
        df = pd.read_sql_query(sql_query, conn)
        conn.close()
        return df
    except Exception as e:
        return f"쿼리 실행 오류: {e}"

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
    
    # 환경변수에 강제 세팅
    import os
    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GOOGLE_API_KEY"] = api_key
    
    genai.configure(api_key=api_key)
    
    def call_gemini_with_fallback(prompt, generation_config=None):
        import threading
        model_flash = genai.GenerativeModel('gemini-2.5-flash')
        model_lite = genai.GenerativeModel('gemini-3.5-flash-lite')
        
        def _call_with_thread(model, timeout):
            class ResultBox:
                result = None
                error = None
            box = ResultBox()
            
            def target():
                try:
                    box.result = model.generate_content(prompt, generation_config=generation_config)
                except Exception as e:
                    box.error = e
                    
            t = threading.Thread(target=target)
            t.daemon = True # 메인 스레드 종료 시 같이 강제 종료되도록 설정 (무한 로딩 방지)
            t.start()
            t.join(timeout)
            
            if t.is_alive():
                raise TimeoutError("API Call Timed Out")
            if box.error:
                raise box.error
            return box.result

        try:
            return _call_with_thread(model_flash, 5) # 5초 대기
        except (TimeoutError, Exception) as e:
            if isinstance(e, TimeoutError) or "429" in str(e) or "quota" in str(e).lower():
                try:
                    return _call_with_thread(model_lite, 5) # 5초 대기
                except TimeoutError:
                    class FallbackResponse:
                        text = "NO_SQL 현재 AI API 서버가 과부하 상태입니다. 잠시 후 다시 시도해 주세요. (타임아웃)"
                    return FallbackResponse()
                except Exception as e3:
                    raise e3
            raise e
    
    # DB에서 실제 자산명/업체명 목록을 가져와서 AI에게 제공
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT asset_name FROM lease_contracts WHERE status = 'ACTIVE' ORDER BY asset_name")
        asset_names = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT company_name FROM lease_contracts WHERE status = 'ACTIVE' ORDER BY company_name")
        company_names = [r[0] for r in cur.fetchall()]
        conn.close()
    except:
        asset_names = []
        company_names = []
    
    # 1단계: 의도 파악 및 SQL 생성
    sql_prompt = f"""
당신은 부동산 자산관리 PostgreSQL 데이터베이스 전문가입니다. 다음 데이터베이스 스키마를 참고하여 사용자의 질문에 답하기 위한 PostgreSQL SQL 쿼리를 작성하세요.
질문이 DB 조회가 필요한 경우, 오직 'SELECT' 쿼리만 작성해야 합니다.
만약 단순 인사말이거나 DB 조회가 전혀 필요 없는 질문이라면, SQL 대신 'NO_SQL'이라고만 답변하세요.

[데이터베이스 스키마]
{get_db_schema()}

[현재 DB에 등록된 자산명 목록 (asset_name)]
{', '.join(asset_names)}

[현재 DB에 등록된 업체명 목록 (company_name)]
{', '.join(company_names[:50])}

[최근 대화 내용 요약 (참고용)]
{chat_history}

[사용자 질문]
{user_message}

답변 작성 규칙:
- PostgreSQL 문법의 순수 SQL 쿼리만 작성하세요. 마크다운(`)이나 설명은 절대 넣지 마세요.
- UPDATE, DELETE, INSERT 등은 절대 금지합니다.
- 테이블명은 소문자 그대로 사용하세요 (lease_contracts, asset_area, rentroll_overrides, contract_history). 큰따옴표를 쓰지 마세요.
- rent_free_details 컬럼은 JSON 배열 문자열입니다. 현재 날짜는 {datetime.now().strftime('%Y-%m-%d')}입니다. '이번달', '다음달', '10월' 등의 의미를 추론하여 적절한 ILIKE 패턴으로 유연하게 검색하세요.
- 사용자가 자산명이나 업체명을 부정확하게 입력할 수 있습니다. 위의 [자산명 목록]과 [업체명 목록]에서 사용자의 입력과 가장 유사한 값을 찾아 ILIKE '%키워드%'로 검색하세요. (예: 사용자가 '본점'이라고 하면 목록에서 'HQ Building'이 가장 유사하므로 asset_name ILIKE '%HQ%')
- status = 'ACTIVE'인 계약만 기본 조회하세요. (퇴점 업체는 제외)
"""
    try:
        sql_response = call_gemini_with_fallback(
            sql_prompt,
            generation_config=genai.GenerationConfig(temperature=0.1)
        )
        
        sql_query = sql_response.text.replace("```sql", "").replace("```", "").strip()
        
        import re
        # 안전장치: AI가 어떤 형태로 큰따옴표를 쓰든 강제로 소문자 변환 및 따옴표 제거
        sql_query = re.sub(r'"([^"]+)"', lambda m: m.group(1).lower(), sql_query)
        
        # 이전 교체 로직 유지 (따옴표 없이 대문자로 쓴 경우 대비)
        sql_query = sql_query.replace('Lease_Contracts', "lease_contracts")
        sql_query = sql_query.replace('Asset_Area', "asset_area")
        sql_query = sql_query.replace('RentRoll_Overrides', "rentroll_overrides")
        sql_query = sql_query.replace('Contract_History', "contract_history")
        
        # 핵심 안전장치: 정규식을 사용해 ILIKE 패턴 안의 한국어/영어 별칭을 실제 DB 값으로 강제 치환
        asset_name_aliases = {
            r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
            r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
            r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
            r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
            r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
        }
        for pattern, real_key in asset_name_aliases.items():
            # 대소문자 무시하고 패턴 매칭하여 실제 키워드로 치환
            sql_query = re.sub(rf"'%([^']*)({pattern})([^']*)%'", f"'%{real_key}%'", sql_query, flags=re.IGNORECASE)
            # % 기호 없이 쓴 경우 (예: ILIKE '본점')
            sql_query = re.sub(rf"'({pattern})'", f"'%{real_key}%'", sql_query, flags=re.IGNORECASE)

        # 디버깅 파일 쓰기 로직 삭제 (무한 루프 방지)
        
        if "타임아웃" in sql_query:
            return "현재 AI API 서버가 과부하 상태입니다. 잠시 후 다시 시도해 주세요. (타임아웃)"
            
        if "NO_SQL" in sql_query.upper() or not sql_query.upper().startswith("SELECT"):
            # DB 쿼리 불필요
            general_prompt = f"""
사용자가 부동산 자산관리 앱 챗봇에게 한 말입니다.
최근 대화: {chat_history}
사용자: {user_message}
부동산 자산관리 맥락에 맞게 전문적이고 친절하게 답변해 주세요.
"""
            return call_gemini_with_fallback(general_prompt).text
        
        # 2단계: 쿼리 실행
        query_result = execute_query(sql_query)
        
        # 에러 발생 시
        if isinstance(query_result, str):
            return f"죄송합니다. 데이터를 조회하는 중 오류가 발생했습니다.\n(내부 참고: `{query_result}`)\n\n생성된 쿼리: `{sql_query}`"
            
        # 결과가 데이터프레임일 때
        result_str = query_result.to_markdown() if not query_result.empty else "조회된 데이터가 없습니다."
        
        # 3단계: 결과 요약 및 자연어 답변 생성
        final_prompt = f"""
당신은 친절하고 전문적인 부동산 자산관리 어시스턴트입니다.
사용자의 질문과 그에 대한 데이터베이스 조회 결과를 바탕으로 자연스럽게 답변해 주세요.

[사용자 질문]
{user_message}

[조회 결과]
{result_str}

답변 작성 지침:
1. 사용자가 이해하기 쉽게 결과를 한글로 요약해서 답변하세요. 표 형태나 글머리 기호 활용이 좋습니다.
2. 금액이나 면적은 가독성 좋게 포맷팅(콤마 등) 해주세요. (면적 단위는 '평', 금액 단위는 문맥에 맞게)
3. 시스템 내부적인 SQL 쿼리문 자체는 사용자에게 구체적으로 보여주지 않아도 됩니다.
"""
        final_response = call_gemini_with_fallback(
            final_prompt,
            generation_config=genai.GenerationConfig(temperature=0.3)
        )
        
        return final_response.text
    except Exception as e:
        return f"죄송합니다. 답변을 생성하는 도중 오류가 발생했습니다: {e}"
