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

import time
_global_tool_state = {"count": 0, "last_time": 0}

def _check_global_tool_limit():
    global _global_tool_state
    now = time.time()
    if now - _global_tool_state["last_time"] > 15:
        _global_tool_state["count"] = 0
    _global_tool_state["count"] += 1
    _global_tool_state["last_time"] = now
    
    if _global_tool_state["count"] > 5:
        return "🚨 [치명적 오류] 도구 호출 한도(5회)를 초과했습니다. 더 이상 어떠한 도구도 호출하지 말고, 사용자에게 '요청이 너무 복잡하여 직접 답변할 수 없습니다.'라고 답변하고 즉시 종료하세요."
    return None

def execute_sql_query(sql_query: str) -> str:
    '''
    데이터베이스에 원시 SQL(SELECT)을 실행하여 결과를 마크다운 표 문자열로 반환합니다.
    단순한 계약 내역, 자산 면적, 보증금 등을 조회할 때 사용하세요.
    연간 임대료 수입이나 렌트롤을 계산할 때는 이 도구 대신 get_annual_rent_roll을 사용하세요.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

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
        return f"쿼리 실행 오류 발생 (문법을 수정하여 재시도 가능): {e}."

def get_annual_rent_roll(year: int, asset_name: str = "") -> str:
    '''
    렌트프리, 중도 입퇴점, 수동 예외조정, 임대료 정기 인상 등을 모두 완벽히 반영하여 계산된
    특정 연도의 렌트롤(월별 임대료 및 관리비 수입 총합) 데이터를 조회합니다.
    사용자가 '연간 임대료 수입', '연간 관리비 수입', '특정 연도의 수입' 등을 물어볼 때 반드시 이 도구를 사용하세요.
    asset_name은 영문자산명(HQ, Busan 등) 혹은 빈 문자열을 입력하세요.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

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
        return f"오류 발생! 절대 재시도하지 말고 사용자에게 사과하세요. 상세: {e}"

def get_contract_details(company_name: str) -> str:
    '''
    특정 임차인(회사명)의 계약 상세 정보(보증금, 임대료, 계약일자 등)를 조회합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        conn = get_db_connection()
        query = """
            SELECT asset_name, floor, company_name, start_date, end_date, 
                   deposit, monthly_rent, monthly_maintenance_fee, rent_free_details, status
            FROM lease_contracts
            WHERE company_name ILIKE %s AND status = 'ACTIVE'
        """
        df = pd.read_sql_query(query, conn, params=('%' + company_name + '%',))
        conn.close()
        if df.empty:
            return f"'{company_name}'에 대한 활성 계약 정보를 찾을 수 없습니다."
        return df.to_markdown()
    except Exception as e:
        return f"오류 발생! 절대 재시도하지 말고 사용자에게 사과하세요. 상세: {e}"

def get_vacancy_status(asset_name: str = "") -> str:
    '''
    특정 자산 또는 전체 자산의 공실률(%)과 현재 비어있는 층(floor)을 조회합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        conn = get_db_connection()
        
        area_query = "SELECT asset_name, floor, total_area FROM asset_area"
        mapped_asset = asset_name
        if asset_name and asset_name.strip() != "":
            import re
            asset_name_aliases = {
                r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
                r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
                r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
                r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
                r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
            }
            for pattern, real_key in asset_name_aliases.items():
                if re.search(pattern, asset_name, re.IGNORECASE):
                    mapped_asset = real_key
                    break
            area_query += f" WHERE asset_name ILIKE '%%{mapped_asset}%%'"
            
        df_area = pd.read_sql_query(area_query, conn)
        
        lease_query = "SELECT asset_name, floor, contract_area FROM lease_contracts WHERE status = 'ACTIVE'"
        if asset_name and asset_name.strip() != "":
            lease_query += f" AND asset_name ILIKE '%%{mapped_asset}%%'"
        df_lease = pd.read_sql_query(lease_query, conn)
        conn.close()
        
        if df_area.empty:
            return "해당 자산의 면적 정보가 존재하지 않습니다."
            
        total_area = df_area['total_area'].sum()
        leased_area = df_lease['contract_area'].sum() if not df_lease.empty else 0
        vacancy_area = total_area - leased_area
        vacancy_rate = (vacancy_area / total_area * 100) if total_area > 0 else 0
        
        df_area['key'] = df_area['asset_name'] + "_" + df_area['floor']
        df_lease['key'] = df_lease['asset_name'] + "_" + df_lease['floor']
        leased_keys = set(df_lease['key'].unique())
        empty_floors_df = df_area[~df_area['key'].isin(leased_keys)]
        
        res = f"[{asset_name or '전체'} 자산 공실 현황]\n"
        res += f"- 총 임대가능면적: {total_area:,.2f} 평\n"
        res += f"- 현재 임대면적: {leased_area:,.2f} 평\n"
        res += f"- 공실률: {vacancy_rate:.1f}%\n"
        
        if not empty_floors_df.empty:
            empty_list = empty_floors_df.apply(lambda row: f"{row['asset_name']} {row['floor']}", axis=1).tolist()
            res += f"- 현재 완전 공실 층: {', '.join(empty_list)}\n"
        else:
            res += "- 현재 완전 공실인 층은 없습니다.\n"
            
        return res
    except Exception as e:
        return f"오류 발생! 절대 재시도하지 말고 사용자에게 사과하세요. 상세: {e}"

def get_expiring_contracts(months_ahead: int = 3) -> str:
    '''
    향후 N개월 이내에 만기가 도래하는 계약 목록을 조회합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        conn = get_db_connection()
        query = f"""
            SELECT asset_name, floor, company_name, end_date, monthly_rent
            FROM lease_contracts
            WHERE status = 'ACTIVE' 
              AND end_date <= CURRENT_DATE + INTERVAL '{months_ahead} months'
              AND end_date >= CURRENT_DATE
            ORDER BY end_date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return f"향후 {months_ahead}개월 이내에 만기가 도래하는 계약이 없습니다."
        return df.to_markdown()
    except Exception as e:
        return f"오류 발생! 절대 재시도하지 말고 사용자에게 사과하세요. 상세: {e}"

def compare_revenue(entity_name: str, entity_type: str, compare_type: str, base_year: int, base_month: int, target_year: int = None, target_month: int = None) -> str:
    '''
    특정 자산(asset) 또는 임차인(company)의 기준월(년) 대비 수익(임대료+관리비)을 비교합니다.
    - entity_type: "asset" 또는 "company"
    - compare_type: "MoM" (전월 대비) 또는 "YoY" (전년 동월 대비) 또는 "YTD" (전년 대비 연간 총수익) 또는 "Custom" (임의의 달 비교)
    base_month: 기준 월 (1~12)
    "Custom"일 경우 target_year와 target_month를 반드시 입력하세요 (예: 2026년 6월 대비 10월 비교면 base가 10월, target이 6월).
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        if compare_type not in ["MoM", "YoY", "YTD", "Custom"]:
            return "compare_type은 'MoM', 'YoY', 'YTD', 'Custom' 중 하나여야 합니다."
            
        sel_assets = None
        sel_companies = None
        
        if entity_type.lower() == "asset":
            import re
            asset_name_aliases = {
                r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
                r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
                r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
                r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
                r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
            }
            mapped_asset = entity_name
            for pattern, real_key in asset_name_aliases.items():
                if re.search(pattern, entity_name, re.IGNORECASE):
                    mapped_asset = real_key
                    break
            sel_assets = [mapped_asset]
        else:
            sel_companies = [entity_name]

        def get_revenue(year, month):
            df_rr, _ = generate_annual_rent_roll(year, sel_assets=sel_assets, sel_companies=sel_companies)
            if df_rr.empty: return 0
            
            if month == "ALL":
                total = 0
                for m in range(1, 13):
                    r_col, m_col = f"{m}월 임대료", f"{m}월 관리비"
                    if r_col in df_rr.columns: total += df_rr[r_col].sum()
                    if m_col in df_rr.columns: total += df_rr[m_col].sum()
                return total
            else:
                r_col, m_col = f"{month}월 임대료", f"{month}월 관리비"
                total = 0
                if r_col in df_rr.columns: total += df_rr[r_col].sum()
                if m_col in df_rr.columns: total += df_rr[m_col].sum()
                return total

        if compare_type == "MoM":
            target_year = base_year if base_month > 1 else base_year - 1
            target_month = base_month - 1 if base_month > 1 else 12
        elif compare_type == "YoY":
            target_year = base_year - 1
            target_month = base_month
        elif compare_type == "YTD":
            target_year = base_year - 1
            target_month = "ALL"
            base_month = "ALL"
        elif compare_type == "Custom":
            if target_year is None or target_month is None:
                return "Custom 비교 시 target_year와 target_month 파라미터가 필요합니다."
            
        rev_base = get_revenue(base_year, base_month)
        rev_target = get_revenue(target_year, target_month)
        
        diff = rev_base - rev_target
        rate = (diff / rev_target * 100) if rev_target > 0 else 0
        
        title_map = {"MoM": "전월 대비", "YoY": "전년 동월 대비", "YTD": "전년 대비 총", "Custom": f"{target_year}년 {target_month}월 대비"}
        title = title_map[compare_type]
        
        res = f"[{entity_name} 수익 비교 ({title})]\n"
        if compare_type == "YTD":
            res += f"- {base_year}년 총수익: {rev_base:,.0f}원\n"
            res += f"- {target_year}년 총수익: {rev_target:,.0f}원\n"
        else:
            res += f"- {base_year}년 {base_month}월 수익: {rev_base:,.0f}원\n"
            res += f"- {target_year}년 {target_month}월 수익: {rev_target:,.0f}원\n"
            
        res += f"- 증감액: {diff:,.0f}원\n"
        res += f"- 증감률: {rate:.1f}%\n"
        
        return res
    except Exception as e:
        return f"오류 발생! 절대 재시도하지 말고 사용자에게 사과하세요. 상세: {e}"

def get_deposit_return_schedule(months_ahead: int = 3) -> str:
    '''
    향후 N개월 이내에 만기가 도래하여 반환해야 할 보증금 총액과 계약 목록을 조회합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        conn = get_db_connection()
        query = f"""
            SELECT asset_name, floor, company_name, end_date, deposit
            FROM lease_contracts
            WHERE status = 'ACTIVE' 
              AND end_date <= CURRENT_DATE + INTERVAL '{months_ahead} months'
              AND end_date >= CURRENT_DATE
            ORDER BY end_date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return f"향후 {months_ahead}개월 이내에 반환 예정인 보증금이 없습니다."
            
        total_deposit = df['deposit'].sum()
        res = f"[향후 {months_ahead}개월 내 보증금 반환 예정액: {total_deposit:,.0f}원]\n\n"
        res += df.to_markdown()
        return res
    except Exception as e:
        return f"오류 발생! 상세: {e}"

def get_rent_per_pyung(entity_name: str, entity_type: str) -> str:
    '''
    특정 자산(asset) 전체 또는 임차인(company)의 계약 면적 대비 평당 임대료와 평당 관리비를 계산합니다.
    entity_type은 "asset" 또는 "company" 중 하나여야 합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        conn = get_db_connection()
        query = """
            SELECT asset_name, floor, company_name, contract_area, monthly_rent, monthly_maintenance_fee
            FROM lease_contracts
            WHERE status = 'ACTIVE'
        """
        if entity_type.lower() == "asset":
            import re
            asset_name_aliases = {
                r'본점|본사|에이치큐|hq빌딩|hq building|hq': 'HQ',
                r'부산': 'Busan', r'둔산': 'Dunsan', r'광주': 'Gwangju',
                r'잠실': 'Jamsilseo', r'송파': 'Songpa', r'철산': 'Cheolsan Town',
                r'춘천': 'Chuncheon', r'분당': 'Bundang', r'포항': 'Pohang',
                r'대전': 'Daejeon', r'침산': 'Chimsan-dong',
            }
            mapped_asset = entity_name
            for pattern, real_key in asset_name_aliases.items():
                if re.search(pattern, entity_name, re.IGNORECASE):
                    mapped_asset = real_key
                    break
            query += f" AND asset_name ILIKE '%%{mapped_asset}%%'"
        elif entity_type.lower() == "company":
            query += f" AND company_name ILIKE '%%{entity_name}%%'"
        else:
            return "entity_type은 'asset' 또는 'company'여야 합니다."
            
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return f"해당 {entity_type}에 대한 활성 계약 정보가 없습니다."
            
        total_area_sqm = df['contract_area'].sum()
        total_area_py = total_area_sqm / 3.3058
        total_rent = df['monthly_rent'].sum()
        total_maint = df['monthly_maintenance_fee'].sum()
        
        if total_area_py <= 0:
            return "계약 면적이 0이어서 평당 단가를 계산할 수 없습니다."
            
        rent_per_py = total_rent / total_area_py
        maint_per_py = total_maint / total_area_py
        
        res = f"[{entity_name} 평당 단가 분석]\n"
        res += f"- 총 계약면적: {total_area_sqm:,.2f}㎡ ({total_area_py:,.2f}평)\n"
        res += f"- 총 월임대료: {total_rent:,.0f}원\n"
        res += f"- 총 월관리비: {total_maint:,.0f}원\n"
        res += f"- 평당 임대료: {rent_per_py:,.0f}원/평\n"
        res += f"- 평당 관리비: {maint_per_py:,.0f}원/평\n"
        res += f"- NOC(평당 총비용): {(rent_per_py + maint_per_py):,.0f}원/평\n"
        return res
    except Exception as e:
        return f"오류 발생! 상세: {e}"

def get_current_rent_free_impact(year: int, month: int) -> str:
    '''
    특정 연월(예: 2026년 10월)에 렌트프리를 적용받는 계약들의 목록과 차감된 총 임대료(기회비용)를 계산합니다.
    '''
    limit_msg = _check_global_tool_limit()
    if limit_msg: return limit_msg

    try:
        from utils import _is_rent_free_month, _parse_rent_free_details
        conn = get_db_connection()
        query = "SELECT asset_name, floor, company_name, start_date, end_date, monthly_rent, rent_free_details FROM lease_contracts WHERE status = 'ACTIVE'"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        impact_list = []
        total_impact = 0
        
        for _, row in df.iterrows():
            rf_details = row['rent_free_details']
            start_d = row['start_date']
            end_d = row['end_date']
            if not rf_details or pd.isna(rf_details): continue
            
            parsed = _parse_rent_free_details(rf_details)
            if not parsed: continue
            
            if _is_rent_free_month(year, month, start_d, end_d, parsed):
                rent = row['monthly_rent']
                total_impact += rent
                impact_list.append({
                    "자산": row['asset_name'],
                    "임차인": row['company_name'],
                    "월임대료_차감액": rent,
                    "렌트프리조건": rf_details
                })
        
        if not impact_list:
            return f"{year}년 {month}월에 렌트프리가 적용되는 계약이 없습니다."
            
        res_df = pd.DataFrame(impact_list)
        res = f"[{year}년 {month}월 렌트프리 기회비용 분석]\n"
        res += f"- 렌트프리로 인해 감소한 임대료 총액: {total_impact:,.0f}원\n\n"
        res += res_df.to_markdown()
        return res
    except Exception as e:
        return f"오류 발생! 상세: {e}"

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
    
    from google import genai as genai_new
    from google.genai import types
    
    client = genai_new.Client(api_key=api_key)
    
    system_instruction = f'''
당신은 친절하고 전문적인 부동산 자산관리 어시스턴트입니다.
사용자의 질문을 파악하여 적절한 도구(Tool)를 사용해 답변하세요.

1. 특정 임차인의 계약 상세정보 조회는 `get_contract_details`를 사용하세요.
2. 특정 자산의 공실 현황이나 공실률을 물어보면 `get_vacancy_status`를 사용하세요.
3. 향후 만기가 도래하는 계약 목록은 `get_expiring_contracts`를 사용하세요.
4. 수익 비교(전월 대비, 전년 대비, 임의의 달 비교) 질문은 반드시 `compare_revenue`를 사용하세요. (임의의 달 비교시에는 compare_type을 'Custom'으로 설정하고 target_year와 target_month를 명시하세요.)
5. 연간 임대료 수입, 렌트롤 총합 등 일반적인 계산은 `get_annual_rent_roll`을 사용하세요.
6. [신규] 보증금 반환 일정 및 향후 반환해야 할 보증금 규모는 `get_deposit_return_schedule`을 사용하세요.
7. [신규] 특정 자산이나 업체의 평당 임대료/관리비 단가 분석은 `get_rent_per_pyung`을 사용하세요.
8. [신규] 특정 월의 렌트프리 적용 업체 목록과 이로 인한 기회비용(감소한 임대료)은 `get_current_rent_free_impact`를 사용하세요.
9. 위 도구들로 해결되지 않는 단순 통계나 기타 조건 검색은 `execute_sql_query`를 사용하세요. (DB 스키마:\n{get_db_schema()})
10. 도구를 호출하여 조회된 결과를 바탕으로 사용자에게 친절하고 이해하기 쉬운 한글 자연어로 답변을 작성하세요.
11. 도구 호출은 최대 5회까지만 가능합니다. 5회 안에 답을 완성하지 못하면 사용자에게 솔직히 말하세요.
'''

    # 사용 가능한 도구 맵 (이름 -> 함수)
    tool_map = {
        "execute_sql_query": execute_sql_query,
        "get_annual_rent_roll": get_annual_rent_roll,
        "get_contract_details": get_contract_details,
        "get_vacancy_status": get_vacancy_status,
        "get_expiring_contracts": get_expiring_contracts,
        "compare_revenue": compare_revenue,
        "get_deposit_return_schedule": get_deposit_return_schedule,
        "get_rent_per_pyung": get_rent_per_pyung,
        "get_current_rent_free_impact": get_current_rent_free_impact,
    }

    # google.genai용 도구 정의
    tool_declarations = []
    for fn_name, fn in tool_map.items():
        # docstring에서 파라미터 정보 추출 대신, 직접 함수 객체를 전달
        tool_declarations.append(fn)

    MAX_TOOL_CALLS = 5

    try:
        prompt = f"[최근 대화 요약]\n{chat_history}\n\n[사용자 질문]\n{user_message}"
        
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tool_declarations,
            temperature=0.3,
        )
        
        tool_call_count = 0

        while tool_call_count <= MAX_TOOL_CALLS:
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=contents,
                config=config,
            )

            # 응답에서 function_call 찾기
            function_call_part = None
            text_response = None
            
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        function_call_part = part
                    elif part.text:
                        text_response = part.text

            # function_call이 없으면 텍스트 응답 반환
            if not function_call_part:
                if text_response:
                    return text_response
                return "죄송합니다, 요청하신 정보를 조회했지만 답변을 생성하지 못했습니다."

            tool_call_count += 1
            fc = function_call_part.function_call
            fn_name = fc.name
            fn_args = dict(fc.args) if fc.args else {}

            # int 타입 변환 (API가 float으로 보내는 경우 대비)
            import inspect
            if fn_name in tool_map:
                sig = inspect.signature(tool_map[fn_name])
                for param_name, param in sig.parameters.items():
                    if param_name in fn_args and param.annotation == int:
                        fn_args[param_name] = int(fn_args[param_name])

            # 도구 실행
            if fn_name in tool_map:
                try:
                    result = tool_map[fn_name](**fn_args)
                except Exception as e:
                    result = f"도구 실행 중 오류가 발생했습니다: {e}"
            else:
                result = f"알 수 없는 도구입니다: {fn_name}"

            # 대화 이력에 모델 응답 + 도구 결과 추가
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(
                    role="tool",
                    parts=[types.Part.from_function_response(
                        name=fn_name,
                        response={"result": str(result)[:3000]}
                    )]
                )
            )

        return "죄송합니다, 조회 횟수를 초과하여 답변을 완성하지 못했습니다. 질문을 좀 더 구체적으로 입력해 주세요."

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            return "죄송합니다. 무료 API 사용량이 초과되었습니다. 잠시 후(약 1분) 다시 질문해 주세요."
        if "503" in error_msg or "unavailable" in error_msg.lower():
            return "죄송합니다. 현재 구글 AI 서버(Gemini)에 전 세계적인 접속자가 몰려 일시적으로 응답이 지연되고 있습니다. 10초 정도 후에 다시 질문해 주시면 정상 작동할 것입니다."
        return f"죄송합니다. 답변을 생성하는 도중 오류가 발생했습니다: {e}"
