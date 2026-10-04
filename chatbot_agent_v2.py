"""부동산 자산관리 DB Q&A 챗봇 에이전트 (Gemini function calling).

구성
- 도구(Tool) 함수: DB를 조회/계산해 모델이 읽을 텍스트를 반환합니다.
- 에이전트 루프: 모델이 요청한 도구(병렬 호출 포함)를 실행하고 결과를 돌려주며,
  최종 답변은 스트리밍으로 UI에 전달합니다.

설계 원칙
- DB 연결은 utils의 SQLAlchemy 커넥션 풀(get_engine)을 재사용합니다.
- 자산명/업체명은 resolve_assets / resolve_companies 한 곳에서만 해석합니다.
- 면적 단위는 앱 전체와 동일하게 '평'입니다.
"""
import inspect
import json
import re
import time
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, text

from utils import (
    CURRENCY_RATES,
    CURRENT_OCCUPANCY_SQL,
    LEASE_ASSUMPTIONS,
    calc_lease_economics_table,
    fetch_data,
    generate_annual_rent_roll,
    get_actual_monthly_rent_by_company,
    get_engine,
    get_floor_vacancy,
    get_upcoming_new_leases_by_floor,
)

MODEL_NAME = "gemini-3.5-flash"
MAX_TOOL_ROUNDS = 5        # 모델 ↔ 도구 왕복 최대 횟수
MAX_TOOL_CALLS = 10        # 한 질문당 도구 실행 최대 횟수(병렬 호출 포함)
MAX_RESULT_CHARS = 12000   # 도구 결과를 모델에 넘길 때의 최대 길이
MAX_TABLE_ROWS = 80        # 표 형태 결과의 최대 행 수
HISTORY_MESSAGES = 6       # 모델에 넘길 직전 대화 메시지 수
SQL_TIMEOUT = "8s"

# 실제 DB 자산명(영문) → 사용자가 부를 수 있는 한글/약칭 별칭
ASSET_ALIASES = {
    "HQ Building": ["본점", "본사", "에이치큐", "HQ빌딩", "HQ", "본점빌딩"],
    "ANSAN": ["안산"],
    "Bangbae-dong": ["방배동", "방배"],
    "Boramae": ["보라매"],
    "Bundang": ["분당"],
    "Busan": ["부산"],
    "Busan Dormitory": ["부산기숙사", "부산 기숙사"],
    "Cheolsan Town": ["철산타운", "철산"],
    "Chimsan-dong": ["침산동", "침산"],
    "Chuncheon": ["춘천"],
    "Daejeon": ["대전"],
    "Deokcheon-dong": ["덕천동", "덕천"],
    "Dunsan": ["둔산"],
    "Family Town": ["패밀리타운", "훼미리타운"],
    "Gangneung": ["강릉"],
    "Gwangju": ["광주"],
    "Hongseong": ["홍성"],
    "Iksan": ["익산"],
    "Jamsilseo": ["잠실서", "잠실"],
    "Jungsan": ["중산"],
    "Macheon-dong": ["마천동", "마천"],
    "Majang-dong": ["마장동", "마장"],
    "Pohang": ["포항"],
    "Sanbon": ["산본"],
    "Sangju": ["상주"],
    "Seosuwon": ["서수원"],
    "Seoul Dormitory": ["서울기숙사", "서울 기숙사"],
    "Songpa": ["송파"],
    "Wolgok-dong": ["월곡동", "월곡"],
    "Wonju": ["원주"],
}

DB_SCHEMA = """
asset_area (자산별 층 면적, 단위: 평)
  asset_name TEXT, floor TEXT ('10F', 'B1F', 'RF' 등), exclusive_area REAL(전용), common_area REAL,
  total_area REAL(임대/계약 기준 면적), bank_area REAL(은행 자체 사용 면적), PK(asset_name, floor)

lease_contracts (임대차 계약)
  contract_id SERIAL PK, asset_name TEXT, floor TEXT(다층 계약은 '20,21' 형태), company_name TEXT,
  contract_date DATE, start_date DATE, end_date DATE,
  contract_area REAL(계약면적, 평), contract_exclusive_area REAL(전용면적, 평),
  deposit REAL(보증금), monthly_rent REAL(최초 월임대료), monthly_maintenance_fee REAL(최초 월관리비),
  currency TEXT('KRW' 또는 'USD'), total_rent_free_months INTEGER,
  rent_free_details TEXT(렌트프리 월 목록 JSON 배열, 예: '["2026-10","2026-11"]'),
  status TEXT('ACTIVE'=최신 계약(갱신 계약은 시작일이 미래일 수 있음), 'RENEWED'=갱신 전 기존 계약(기간이 남아 있으면 현재도 점유 중), 'TERMINATED'=중도 해지),
  deposit_return_date DATE, penalty_yn TEXT, penalty_amount REAL, parent_contract_id INTEGER,
  floor_details TEXT(층별 면적 JSON, 예: '{"20F": {"area": 687.3, "exclusive_area": 429.3, "ratio": 0.78}}'),
  escalation_cycle_years INTEGER, rent_inc_rate REAL, maint_inc_rate REAL,
  rent_schedule TEXT(인상 반영 기간별 임대료 JSON), remarks TEXT

rentroll_overrides (렌트롤 수동 조정값)
  contract_id INTEGER, floor TEXT, year INTEGER, month INTEGER, over_rent REAL, over_maint REAL

contract_history (계약 변경 이력)
  history_id SERIAL PK, contract_id INTEGER, action_type TEXT, action_date DATE, action_month TEXT, details TEXT
"""

TOOL_LABELS = {
    "execute_sql_query": "DB 직접 조회",
    "get_annual_rent_roll": "연간 렌트롤 계산",
    "get_contract_details": "계약 상세 조회",
    "get_vacancy_status": "공실 현황 계산",
    "get_expiring_contracts": "만기 도래 계약 조회",
    "compare_revenue": "수익 비교 계산",
    "get_deposit_return_schedule": "보증금 반환 일정 조회",
    "get_rent_per_pyung": "평당 단가 계산",
    "get_current_rent_free_impact": "렌트프리 현황 계산",
}


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _norm(s) -> str:
    """비교용 정규화: 공백, 하이픈, 괄호, 밑줄 제거 후 소문자."""
    return re.sub(r"[\s\-_()]", "", str(s)).lower()


def _all_asset_names() -> list:
    # fetch_data 캐시는 데이터 저장 시 비워지므로 여기서 별도 캐시를 두지 않습니다.
    df = fetch_data(
        "SELECT DISTINCT asset_name FROM asset_area "
        "UNION SELECT DISTINCT asset_name FROM lease_contracts"
    )
    return sorted(n for n in df["asset_name"].dropna().unique() if str(n).strip())


def _all_company_names() -> list:
    df = fetch_data("SELECT DISTINCT company_name FROM lease_contracts")
    return sorted(n for n in df["company_name"].dropna().unique() if str(n).strip())


def resolve_assets(name: str):
    """사용자 입력 자산명을 실제 DB 자산명 리스트로 변환합니다.

    반환값: None(입력 없음 = 전체), [] (찾지 못함), [자산명, ...]
    """
    if name is None or not str(name).strip() or _norm(name) in ("전체", "all", "모든자산"):
        return None
    names = _all_asset_names()
    key = _norm(name)

    # 1) DB 자산명과 정확히 일치
    for n in names:
        if _norm(n) == key:
            return [n]

    # 2) 별칭 매칭: 입력에 포함된 별칭 중 가장 긴 것을 선택 ('부산기숙사'가 '부산'보다 우선)
    best = None
    for real, aliases in ASSET_ALIASES.items():
        for alias in aliases + [real]:
            a = _norm(alias)
            if a and a in key and (best is None or len(a) > best[0]):
                best = (len(a), real)
    if best and best[1] in names:
        return [best[1]]

    # 3) DB 자산명 부분 일치
    return [n for n in names if key in _norm(n)]


def resolve_companies(name: str) -> list:
    """업체명 부분 일치 검색 (공백/괄호/하이픈 무시)."""
    key = _norm(name)
    if not key:
        return []
    return [c for c in _all_company_names() if key in _norm(c)]


def _asset_not_found(name: str) -> str:
    return (
        f"'{name}'에 해당하는 자산을 찾지 못했습니다. "
        f"사용 가능한 자산명: {', '.join(_all_asset_names())}. 올바른 자산명으로 다시 호출하세요."
    )


def _company_not_found(name: str) -> str:
    return (
        f"'{name}'이(가) 포함된 업체명을 찾지 못했습니다. "
        "업체명의 핵심 단어만으로 다시 검색하거나, execute_sql_query로 company_name을 ILIKE 검색해 보세요."
    )


def _read_sql(sql: str, params: Optional[dict] = None, expanding: tuple = ()) -> pd.DataFrame:
    """파라미터 바인딩 조회. expanding에 지정한 파라미터는 리스트를 IN 절로 확장합니다."""
    stmt = text(sql)
    if expanding:
        stmt = stmt.bindparams(*[bindparam(p, expanding=True) for p in expanding])
    with get_engine().connect() as conn:
        return pd.read_sql(stmt, conn, params=params or {})


def _df_to_text(df: pd.DataFrame, max_rows: int = MAX_TABLE_ROWS) -> str:
    if df is None or df.empty:
        return "조회된 데이터가 없습니다."
    n = len(df)
    out = df.head(max_rows).to_markdown(index=False, floatfmt=",.2f")
    if n > max_rows:
        out += f"\n\n(총 {n}행 중 상위 {max_rows}행만 표시. 전체 합계는 집계 쿼리나 계산 도구를 사용하세요.)"
    else:
        out += f"\n\n(총 {n}행)"
    return out


def _fx(currency) -> float:
    return CURRENCY_RATES["USD_TO_KRW"] if str(currency).upper() == "USD" else 1.0


def _to_krw(val, currency) -> float:
    if val is None or pd.isna(val):
        return 0.0
    return float(val) * _fx(currency)


def _won(v: float) -> str:
    """금액을 '12,345,678원 (약 1,234.6만원)' 형태로 표시."""
    v = float(v or 0)
    if abs(v) >= 1e8:
        return f"{v:,.0f}원 (약 {v / 1e8:,.2f}억원)"
    if abs(v) >= 1e4:
        return f"{v:,.0f}원 (약 {v / 1e4:,.0f}만원)"
    return f"{v:,.0f}원"


def _parse_json(val):
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return None
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return None


def _data_version(year: int) -> str:
    """계약/수동조정 데이터의 지문. 앱에서 데이터를 저장하면 fetch_data 캐시가 비워져 값이 바뀝니다."""
    df_c = fetch_data("SELECT * FROM Lease_Contracts")
    df_o = fetch_data(f"SELECT * FROM RentRoll_Overrides WHERE year = {int(year)}")
    h = int(pd.util.hash_pandas_object(df_c.astype(str), index=False).sum()) if not df_c.empty else 0
    h2 = int(pd.util.hash_pandas_object(df_o.astype(str), index=False).sum()) if not df_o.empty else 0
    return f"{len(df_c)}:{h}:{len(df_o)}:{h2}"


def _cached_rent_roll(year: int, assets: Optional[tuple], companies: Optional[tuple]) -> pd.DataFrame:
    """렌트롤은 (연도, 자산, 업체, 데이터 지문) 조합별로 캐시합니다. 데이터가 바뀌면 지문이 달라져 다시 계산합니다."""
    return _rent_roll_by_version(int(year), assets, companies, _data_version(year))


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def _rent_roll_by_version(year: int, assets: Optional[tuple], companies: Optional[tuple], version_key: str) -> pd.DataFrame:
    """항상 1~12월 전체를 계산합니다."""
    df, _ = generate_annual_rent_roll(
        year,
        sel_assets=list(assets) if assets else None,
        sel_companies=list(companies) if companies else None,
        start_month=1,
    )
    return df


def _sum_months(df: pd.DataFrame, months) -> tuple:
    """렌트롤에서 지정한 월들의 (임대료, 관리비) 합계를 원화로 반환."""
    if df is None or df.empty:
        return 0.0, 0.0
    fx = df["통화"].map(_fx) if "통화" in df.columns else 1.0
    rent = maint = 0.0
    for m in months:
        if f"{m}월 임대료" in df.columns:
            rent += float((df[f"{m}월 임대료"] * fx).sum())
        if f"{m}월 관리비" in df.columns:
            maint += float((df[f"{m}월 관리비"] * fx).sum())
    return rent, maint


# ---------------------------------------------------------------------------
# 도구 함수 (docstring이 모델에게 전달되는 도구 설명입니다)
# ---------------------------------------------------------------------------
def execute_sql_query(sql_query: str) -> str:
    """전용 도구로 해결되지 않는 조회를 위해 PostgreSQL SELECT 쿼리를 읽기 전용으로 실행합니다.

    임차인 목록, 조건 검색, 단순 집계 등에 사용하세요. 실제 월별 임대료 수입(인상, 렌트프리,
    수동조정 반영)은 이 도구 대신 get_annual_rent_roll 또는 compare_revenue를 사용하세요.
    자산명은 반드시 영문 DB 자산명(예: 'HQ Building')을 사용하세요.

    Args:
        sql_query: 실행할 단일 SELECT(또는 WITH) 쿼리. 세미콜론으로 여러 문장을 이어 쓰지 마세요.
    """
    sql = (sql_query or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql):
        return "오류: 조회(SELECT/WITH) 쿼리만 실행할 수 있습니다."
    if ";" in sql:
        return "오류: 한 번에 하나의 쿼리만 실행할 수 있습니다. 세미콜론을 제거하고 다시 시도하세요."
    # 모델이 "Lease_Contracts"처럼 따옴표 식별자를 쓰면 PostgreSQL에서 대소문자가 구분되므로 소문자화
    sql = re.sub(r'"([A-Za-z_][A-Za-z0-9_]*)"', lambda m: m.group(1).lower(), sql)
    try:
        # DBAPI 커서를 직접 사용합니다. 파라미터 없이 실행해야 LIKE '%..%'의 '%'가 포맷 문자로 해석되지 않습니다.
        raw = get_engine().raw_connection()
        try:
            cur = raw.cursor()
            # 읽기 전용 트랜잭션 + 타임아웃: LLM이 만든 쿼리가 데이터를 바꾸거나 오래 걸리지 않도록 차단
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = '{SQL_TIMEOUT}'")
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(2000)
            cur.close()
        finally:
            raw.rollback()
            raw.close()  # 풀에 반환
        return _df_to_text(pd.DataFrame(rows, columns=cols))
    except Exception as e:
        msg = str(e).split("\n[SQL")[0][:600]
        return (
            f"쿼리 실행 오류: {msg}\n"
            "스키마의 테이블/컬럼명과 문법을 확인해 쿼리를 수정한 뒤 다시 시도하세요."
        )


def get_annual_rent_roll(year: int, asset_name: str = "") -> str:
    """특정 연도의 월별 임대료/관리비 수입(렌트롤)을 계산합니다.

    렌트프리, 중도 입퇴점 일할 계산, 임대료 인상 스케줄, 수동 조정값이 모두 반영된 실제 청구 기준입니다.
    '올해 임대료 수입', '연간 관리비', '월별 수입' 같은 질문에 사용하세요.

    Args:
        year: 조회 연도 (예: 2026)
        asset_name: 자산명(한글 별칭 가능, 예: '본점'). 비우면 전체 자산.
    """
    try:
        assets = resolve_assets(asset_name)
        if assets == []:
            return _asset_not_found(asset_name)
        df = _cached_rent_roll(int(year), tuple(assets) if assets else None, None)
        if df.empty:
            return f"{year}년에 해당하는 렌트롤 데이터가 없습니다."

        label = ", ".join(assets) if assets else "전체 자산"
        lines = [f"[{year}년 렌트롤 (자산: {label}, 원화 환산, 1~12월)]"]
        total_rent = total_maint = 0.0
        for m in range(1, 13):
            r, mt = _sum_months(df, [m])
            total_rent += r
            total_maint += mt
            lines.append(f"- {m}월: 임대료 {r:,.0f}원 / 관리비 {mt:,.0f}원")
        lines.append(f"\n=> 연간 임대료 합계: {_won(total_rent)}")
        lines.append(f"=> 연간 관리비 합계: {_won(total_maint)}")
        lines.append(f"=> 연간 총수입: {_won(total_rent + total_maint)}")

        if not assets and "자산명" in df.columns:
            fx = df["통화"].map(_fx) if "통화" in df.columns else 1.0
            rent_cols = [f"{m}월 임대료" for m in range(1, 13) if f"{m}월 임대료" in df.columns]
            maint_cols = [f"{m}월 관리비" for m in range(1, 13) if f"{m}월 관리비" in df.columns]
            by_asset = pd.DataFrame({
                "자산명": df["자산명"],
                "연간임대료": df[rent_cols].sum(axis=1) * fx,
                "연간관리비": df[maint_cols].sum(axis=1) * fx,
            }).groupby("자산명", as_index=False).sum()
            by_asset["연간총수입"] = by_asset["연간임대료"] + by_asset["연간관리비"]
            by_asset = by_asset.sort_values("연간총수입", ascending=False)
            lines.append("\n[자산별 연간 수입]\n" + _df_to_text(by_asset.round(0)))
        return "\n".join(lines)
    except Exception as e:
        return f"렌트롤 계산 중 오류가 발생했습니다: {e}"


def get_contract_details(company_name: str, include_inactive: bool = False) -> str:
    """특정 임차인(업체명 일부만 입력해도 됨)의 계약 상세(층, 면적, 기간, 보증금, 임대료, 렌트프리 등)를 조회합니다.

    Args:
        company_name: 업체명 또는 업체명의 일부 (예: '하나플러스')
        include_inactive: True면 갱신 전/해지된 과거 계약도 포함
    """
    try:
        names = resolve_companies(company_name)
        if not names:
            return _company_not_found(company_name)
        sql = """
            SELECT asset_name, floor, company_name, status, start_date, end_date,
                   contract_area AS 계약면적_평, contract_exclusive_area AS 전용면적_평,
                   deposit, monthly_rent, monthly_maintenance_fee, currency,
                   rent_free_details, escalation_cycle_years, rent_inc_rate, remarks
            FROM lease_contracts
            WHERE company_name IN :names
        """
        if not include_inactive:
            sql += " AND status = 'ACTIVE'"
        sql += " ORDER BY company_name, asset_name, start_date"
        df = _read_sql(sql, {"names": names}, expanding=("names",))
        if df.empty:
            return f"'{company_name}'의 활성 계약이 없습니다. (매칭 업체: {', '.join(names)}) include_inactive=True로 과거 계약을 확인할 수 있습니다."
        header = f"[매칭된 업체: {', '.join(names[:10])}{' 외' if len(names) > 10 else ''}]\n"
        return header + _df_to_text(df)
    except Exception as e:
        return f"계약 조회 중 오류가 발생했습니다: {e}"


def get_vacancy_status(asset_name: str = "") -> str:
    """오늘 기준 공실 현황을 계산합니다: 물리적 공실, 입주 예정(계약 완료) 면적, 모집 가능 공실과 각각의 비율.

    '자산별 통합 조회' 화면과 같은 기준이며 단위는 평(전용면적)입니다.
    - 물리적 공실 = 임대가능면적(전용 - 은행 사용) - 현재 점유 면적
    - 입주 예정 = 계약은 체결됐지만 아직 입주 전인 신규 임차 면적 (기존 임차인의 갱신 계약은 제외)
    - 모집 가능 공실 = 물리적 공실 - 입주 예정. 중개사에 안내할 실제 모집 대상입니다.
    '공실 몇 평 남았어', '모집 가능한 공실', '중개사에 안내할 공실' 같은 질문에 사용하세요.

    Args:
        asset_name: 자산명(한글 별칭 가능). 비우면 전체 자산을 자산별로 요약.
    """
    try:
        assets = resolve_assets(asset_name)
        if assets == []:
            return _asset_not_found(asset_name)
        df = get_floor_vacancy(assets)
        df = df[df["rentable"] > 0]
        if df.empty:
            return "해당 자산의 면적 정보가 없습니다."

        rentable = df["rentable"].sum()
        vacant = df["vacant"].sum()
        reserved = df["reserved"].sum()
        marketable = df["marketable"].sum()
        pct = lambda x: (x / rentable * 100) if rentable else 0.0

        label = ", ".join(assets) if assets else "전체 자산"
        res = [
            f"[{label} 공실 현황 (오늘 {date.today():%Y-%m-%d} 기준, 전용면적 기준, 단위: 평)]",
            f"- 임대가능면적: {rentable:,.2f}평",
            f"- 현재 임대면적: {rentable - vacant:,.2f}평",
            f"- 물리적 공실: {vacant:,.2f}평 (공실률 {pct(vacant):.1f}%)",
            f"- 입주 예정(계약 완료, 미입주): {reserved:,.2f}평",
            f"- 모집 가능 공실: {marketable:,.2f}평 (모집 가능 공실률 {pct(marketable):.1f}%)",
        ]

        if not assets:
            g = df.groupby("asset_name", as_index=False)[["rentable", "vacant", "reserved", "marketable"]].sum()
            g["공실률(%)"] = (g["vacant"] / g["rentable"] * 100).round(1)
            g["모집가능 공실률(%)"] = (g["marketable"] / g["rentable"] * 100).round(1)
            g = g.rename(columns={"asset_name": "자산", "rentable": "임대가능(평)", "vacant": "물리적 공실(평)",
                                  "reserved": "입주예정(평)", "marketable": "모집가능 공실(평)"})
            res.append("\n[자산별 공실]\n" + _df_to_text(g.sort_values("공실률(%)", ascending=False)))
        else:
            vac = df[df["vacant"] > 0.5].copy()
            if vac.empty:
                res.append("- 공실이 있는 층이 없습니다.")
            else:
                vac["상태"] = [
                    "완전 공실" if l <= 0.01 else "부분 공실" for l in vac["leased"]
                ]
                vac = vac.rename(columns={"asset_name": "자산", "floor": "층", "rentable": "임대가능(평)",
                                          "leased": "임대(평)", "vacant": "물리적 공실(평)",
                                          "reserved": "입주예정(평)", "marketable": "모집가능 공실(평)"})
                res.append("\n[공실이 있는 층]\n" + _df_to_text(vac[[
                    "자산", "층", "임대가능(평)", "임대(평)", "물리적 공실(평)", "입주예정(평)", "모집가능 공실(평)", "상태"
                ]]))

        up = get_upcoming_new_leases_by_floor()
        if assets:
            up = up[up["asset_name"].isin(assets)]
        if not up.empty:
            up = up.rename(columns={"asset_name": "자산", "floor": "층", "company_name": "입주 예정 업체",
                                    "leased_area": "전용면적(평)", "start_date": "입주(계약 시작)일"})
            res.append("\n[입주 예정 신규 계약]\n" + _df_to_text(up.sort_values("입주(계약 시작)일")))
        return "\n".join(res)
    except Exception as e:
        return f"공실 계산 중 오류가 발생했습니다: {e}"


def get_expiring_contracts(months_ahead: int = 3, asset_name: str = "") -> str:
    """오늘부터 N개월 이내에 만기가 도래하는 유효(ACTIVE) 계약 목록을 조회합니다.

    Args:
        months_ahead: 조회할 개월 수 (예: 3)
        asset_name: 자산명(한글 별칭 가능). 비우면 전체 자산.
    """
    try:
        assets = resolve_assets(asset_name)
        if assets == []:
            return _asset_not_found(asset_name)
        sql = """
            SELECT asset_name, floor, company_name, end_date, contract_area AS 계약면적_평,
                   deposit, monthly_rent, monthly_maintenance_fee, currency
            FROM lease_contracts
            WHERE status = 'ACTIVE'
              AND end_date >= CURRENT_DATE
              AND end_date <= CURRENT_DATE + make_interval(months => :m)
        """
        params = {"m": int(months_ahead)}
        expanding = ()
        if assets:
            sql += " AND asset_name IN :assets"
            params["assets"] = assets
            expanding = ("assets",)
        sql += " ORDER BY end_date"
        df = _read_sql(sql, params, expanding)
        if df.empty:
            return f"오늘({date.today():%Y-%m-%d})부터 {months_ahead}개월 이내에 만기가 도래하는 계약이 없습니다."
        return f"[오늘({date.today():%Y-%m-%d})부터 {months_ahead}개월 이내 만기 계약]\n" + _df_to_text(df)
    except Exception as e:
        return f"만기 계약 조회 중 오류가 발생했습니다: {e}"


def compare_revenue(
    entity_name: str,
    entity_type: str,
    compare_type: str,
    base_year: int,
    base_month: int = 0,
    target_year: Optional[int] = None,
    target_month: Optional[int] = None,
) -> str:
    """자산, 임차인 또는 전체 포트폴리오의 수익(임대료+관리비, 렌트롤 기준)을 기간별로 비교합니다.

    Args:
        entity_name: 자산명(한글 별칭 가능) 또는 업체명(일부). entity_type이 'all'이면 빈 문자열.
        entity_type: 'asset', 'company', 'all'(전체 포트폴리오) 중 하나
        compare_type: 'MoM'(전월 대비), 'YoY'(전년 동월 대비), 'YTD'(1월~기준월 누계 vs 전년 동기),
            'Annual'(연간 총액 vs 전년), 'Custom'(임의의 두 달 비교) 중 하나
        base_year: 기준 연도
        base_month: 기준 월(1~12). Annual이면 0.
        target_year: Custom일 때 비교 대상 연도
        target_month: Custom일 때 비교 대상 월. 예: '6월 대비 10월'이면 base=10월, target=6월
    """
    try:
        ct = (compare_type or "").strip().lower()
        if ct not in ("mom", "yoy", "ytd", "annual", "custom"):
            return "compare_type은 'MoM', 'YoY', 'YTD', 'Annual', 'Custom' 중 하나여야 합니다."
        by, bm = int(base_year), int(base_month or 0)
        if ct in ("mom", "yoy", "custom") and not 1 <= bm <= 12:
            return "base_month(1~12)를 지정해야 합니다."

        assets = companies = None
        et = (entity_type or "").strip().lower()
        label = "전체 포트폴리오"
        if et == "asset":
            assets = resolve_assets(entity_name)
            if assets == []:
                return _asset_not_found(entity_name)
            label = ", ".join(assets) if assets else label
        elif et == "company":
            companies = resolve_companies(entity_name)
            if not companies:
                return _company_not_found(entity_name)
            label = ", ".join(companies)
        elif et != "all":
            return "entity_type은 'asset', 'company', 'all' 중 하나여야 합니다."

        a_key = tuple(assets) if assets else None
        c_key = tuple(companies) if companies else None

        if ct == "mom":
            base = (by, [bm], f"{by}년 {bm}월")
            ty, tm = (by, bm - 1) if bm > 1 else (by - 1, 12)
            target = (ty, [tm], f"{ty}년 {tm}월")
        elif ct == "yoy":
            base = (by, [bm], f"{by}년 {bm}월")
            target = (by - 1, [bm], f"{by - 1}년 {bm}월")
        elif ct == "ytd":
            m = bm if 1 <= bm <= 12 else 12
            base = (by, list(range(1, m + 1)), f"{by}년 1~{m}월 누계")
            target = (by - 1, list(range(1, m + 1)), f"{by - 1}년 1~{m}월 누계")
        elif ct == "annual":
            base = (by, list(range(1, 13)), f"{by}년 연간")
            target = (by - 1, list(range(1, 13)), f"{by - 1}년 연간")
        else:
            if target_year is None or target_month is None:
                return "Custom 비교에는 target_year와 target_month가 필요합니다."
            ty, tm = int(target_year), int(target_month)
            base = (by, [bm], f"{by}년 {bm}월")
            target = (ty, [tm], f"{ty}년 {tm}월")

        def revenue(period):
            year, months, _ = period
            return _sum_months(_cached_rent_roll(year, a_key, c_key), months)

        br, bmt = revenue(base)
        tr, tmt = revenue(target)
        b_total, t_total = br + bmt, tr + tmt
        diff = b_total - t_total

        res = [
            f"[{label} 수익 비교: {base[2]} vs {target[2]} (렌트롤 기준, 원화 환산)]",
            f"- {base[2]}: 총 {_won(b_total)} (임대료 {br:,.0f} / 관리비 {bmt:,.0f})",
            f"- {target[2]}: 총 {_won(t_total)} (임대료 {tr:,.0f} / 관리비 {tmt:,.0f})",
            f"- 증감액: {diff:+,.0f}원",
        ]
        if t_total > 0:
            res.append(f"- 증감률: {diff / t_total * 100:+.1f}%")
        else:
            res.append("- 증감률: 비교 기간 수익이 0원이라 계산할 수 없습니다.")
        return "\n".join(res)
    except Exception as e:
        return f"수익 비교 중 오류가 발생했습니다: {e}"


def get_deposit_return_schedule(months_ahead: int = 3, asset_name: str = "") -> str:
    """오늘부터 N개월 이내 만기로 반환해야 할 보증금 총액과 계약 목록을 조회합니다.

    Args:
        months_ahead: 조회할 개월 수
        asset_name: 자산명(한글 별칭 가능). 비우면 전체 자산.
    """
    try:
        assets = resolve_assets(asset_name)
        if assets == []:
            return _asset_not_found(asset_name)
        sql = """
            SELECT asset_name, floor, company_name, end_date, deposit, currency
            FROM lease_contracts
            WHERE status = 'ACTIVE'
              AND end_date >= CURRENT_DATE
              AND end_date <= CURRENT_DATE + make_interval(months => :m)
        """
        params = {"m": int(months_ahead)}
        expanding = ()
        if assets:
            sql += " AND asset_name IN :assets"
            params["assets"] = assets
            expanding = ("assets",)
        sql += " ORDER BY end_date"
        df = _read_sql(sql, params, expanding)
        if df.empty:
            return f"오늘부터 {months_ahead}개월 이내에 반환 예정인 보증금이 없습니다."
        total = sum(_to_krw(d, c) for d, c in zip(df["deposit"], df["currency"]))
        return (
            f"[오늘({date.today():%Y-%m-%d})부터 {months_ahead}개월 이내 보증금 반환 예정액: {_won(total)}]\n\n"
            + _df_to_text(df)
        )
    except Exception as e:
        return f"보증금 일정 조회 중 오류가 발생했습니다: {e}"


def _unit_metrics(g: pd.DataFrame) -> dict:
    """계약 묶음의 평당 지표 (면적가중). 면적이 0인 계약(전광판 등)은 해당 지표 계산에서 제외."""
    ga = g[g["contract_area"] > 0]
    ge = g[g["contract_exclusive_area"] > 0]
    ca, ea = ga["contract_area"].sum(), ge["contract_exclusive_area"].sum()
    face = ga["face_rent_krw"].sum()
    eff = ga["eff_rent_krw"].sum()
    return {
        "계약수": len(g),
        "계약면적(평)": round(ca, 2),
        "전용면적(평)": round(ea, 2),
        "평당 현재 임대료": round(ga["current_rent_krw"].sum() / ca) if ca else None,
        "평당 유효 임대료": round(eff / ca) if ca else None,
        "렌트프리 할인율(%)": round((1 - eff / face) * 100, 1) if face else None,
        "평당 관리비": round(ga["maint_krw"].sum() / ca) if ca else None,
        "NOC(평당)": round(ga["occupancy_cost_krw"].sum() / ca) if ca else None,
    }


def get_rent_per_pyung(entity_name: str = "", entity_type: str = "asset", deposit_yield_pct: Optional[float] = None) -> str:
    """현재 점유 중인 계약 기준으로 평당 임대료, 유효 임대료(Effective Rent), NOC(실질 임차비용)를 계산합니다.

    - 평당 현재 임대료: 오늘 시점의 스케줄상 월 임대료 / 계약면적 (표면 임대료)
    - 평당 유효 임대료: 계약 전체 기간 평균 월 임대료(렌트프리 월은 0, 인상·일할 반영) / 계약면적
    - 렌트프리 할인율: 계약기간 표면 임대료 대비 렌트프리로 줄어든 비율
    - NOC: (유효 임대료 + 관리비 + 보증금 × 운용이율 / 12) / 계약면적(전체면적)  (사내 기준)
    평당 단가, 실질 임대료, 렌트프리 감안 수익성, NOC 질문에 사용하세요. 모든 금액은 원화 환산, 월 기준입니다.

    Args:
        entity_name: 자산명(한글 별칭 가능) 또는 업체명(일부). 비우면 전체 자산을 자산별로 비교.
        entity_type: 'asset' 또는 'company'
        deposit_yield_pct: 보증금 운용이율(연 %, 예: 5). 생략하면 시스템 기본값을 사용합니다.
    """
    try:
        dy = (float(deposit_yield_pct) / 100) if deposit_yield_pct is not None else LEASE_ASSUMPTIONS["DEPOSIT_YIELD"]
        df = fetch_data(f"SELECT * FROM lease_contracts WHERE {CURRENT_OCCUPANCY_SQL}").copy()
        et = (entity_type or "asset").strip().lower()
        label = "전체 자산"
        has_entity = bool(entity_name and entity_name.strip())
        if has_entity:
            if et == "asset":
                assets = resolve_assets(entity_name)
                if assets == []:
                    return _asset_not_found(entity_name)
                df = df[df["asset_name"].isin(assets)]
                label = ", ".join(assets)
            elif et == "company":
                companies = resolve_companies(entity_name)
                if not companies:
                    return _company_not_found(entity_name)
                df = df[df["company_name"].isin(companies)]
                label = ", ".join(companies)
            else:
                return "entity_type은 'asset' 또는 'company'여야 합니다."

        econ = calc_lease_economics_table(df, deposit_yield=dy)
        if econ.empty:
            return "현재 점유 중인 계약이 없어 단가를 계산할 수 없습니다."
        for c in ("contract_area", "contract_exclusive_area"):
            econ[c] = pd.to_numeric(econ[c], errors="coerce").fillna(0)

        m = _unit_metrics(econ)
        fmt = lambda v, unit="원/평": f"{v:,.0f}{unit}" if v is not None else "계산 불가(면적 없음)"
        res = [
            f"[{label} 평당 단가 및 NOC (오늘 {date.today():%Y-%m-%d} 점유 계약 {m['계약수']}건, 원화 환산, 월 기준)]",
            f"- 계약면적 {m['계약면적(평)']:,.2f}평 / 전용면적 {m['전용면적(평)']:,.2f}평",
            f"- 평당 현재 임대료(표면): {fmt(m['평당 현재 임대료'])}",
            f"- 평당 유효 임대료(계약기간 평균, 렌트프리·인상 반영): {fmt(m['평당 유효 임대료'])}",
            f"- 렌트프리 할인율: {m['렌트프리 할인율(%)']}%" if m["렌트프리 할인율(%)"] is not None else "- 렌트프리 할인율: 계산 불가",
            f"- 평당 관리비(계약기간 평균): {fmt(m['평당 관리비'])}",
            f"- NOC(전체면적 평당, 보증금 운용이율 {dy * 100:.1f}% 가정): {fmt(m['NOC(평당)'])}",
            "※ 평당 임대료·관리비·NOC 모두 계약면적(전체면적) 기준입니다.",
        ]

        group_col = "company_name" if has_entity else "asset_name"
        rows = []
        for key, g in econ.groupby(group_col):
            rows.append({"자산" if group_col == "asset_name" else "업체": key, **_unit_metrics(g)})
        detail = pd.DataFrame(rows)
        if not detail.empty:
            detail = detail.sort_values("NOC(평당)", ascending=False, na_position="last")
            # 숫자는 천 단위 콤마로, 계산 불가(빈 값)는 "-"로 표시
            for col in detail.columns[1:]:
                is_pct = "%" in col
                detail[col] = [
                    "-" if pd.isna(v) else (f"{v:,.1f}" if is_pct else (f"{v:,.2f}" if "면적" in col else f"{v:,.0f}"))
                    for v in detail[col]
                ]
            res.append("\n[상세]\n" + _df_to_text(detail))
        return "\n".join(res)
    except Exception as e:
        return f"평당 단가 계산 중 오류가 발생했습니다: {e}"


def get_current_rent_free_impact(year: int, month: int, asset_name: str = "") -> str:
    """특정 연월에 렌트프리(임대료 면제)가 적용되는 계약 목록과 면제된 임대료 총액(기회비용)을 계산합니다.

    '10월 본점 렌트프리 업체', '다음달 렌트프리 적용 업체' 같은 질문에 사용하세요.

    Args:
        year: 연도 (예: 2026)
        month: 월 (1~12)
        asset_name: 자산명(한글 별칭 가능). 비우면 전체 자산.
    """
    try:
        y, m = int(year), int(month)
        if not 1 <= m <= 12:
            return "month는 1~12 사이여야 합니다."
        assets = resolve_assets(asset_name)
        if assets == []:
            return _asset_not_found(asset_name)

        df = fetch_data(
            "SELECT * FROM lease_contracts "
            "WHERE rent_free_details IS NOT NULL AND rent_free_details NOT IN ('', '[]')"
        )
        if assets:
            df = df[df["asset_name"].isin(assets)]

        month_str = f"{y}-{m:02d}"
        month_start = pd.Timestamp(y, m, 1)
        month_end = month_start + pd.offsets.MonthEnd(0)
        items = []
        for _, row in df.iterrows():
            rf = _parse_json(row["rent_free_details"])
            if not isinstance(rf, list) or month_str not in rf:
                continue
            start, end = pd.to_datetime(row["start_date"]), pd.to_datetime(row["end_date"])
            if pd.isna(start) or pd.isna(end) or start > month_end or end < month_start:
                continue
            # 렌트프리가 없었다면 청구됐을 금액(인상 스케줄, 일할 반영)
            rent, _ = get_actual_monthly_rent_by_company(
                pd.DataFrame([row]), row["asset_name"], row["floor"], row["company_name"], y, m,
                ignore_rent_free=True,
            )
            items.append({
                "자산": row["asset_name"],
                "층": row["floor"],
                "임차인": row["company_name"],
                "면제 임대료(원)": round(_to_krw(rent, row.get("currency", "KRW"))),
                "렌트프리 전체 기간": ", ".join(rf),
                "계약상태": row["status"],
            })

        label = ", ".join(assets) if assets else "전체 자산"
        if not items:
            return f"{y}년 {m}월에 {label}에서 렌트프리가 적용되는 계약이 없습니다."
        res_df = pd.DataFrame(items).sort_values(["자산", "층"])
        total = res_df["면제 임대료(원)"].sum()
        return (
            f"[{y}년 {m}월 렌트프리 적용 계약 ({label})]\n"
            f"- 적용 계약 수: {len(res_df)}건\n"
            f"- 면제된 임대료 총액(기회비용): {_won(total)} (관리비는 렌트프리 대상 아님)\n\n"
            + _df_to_text(res_df)
        )
    except Exception as e:
        return f"렌트프리 계산 중 오류가 발생했습니다: {e}"


TOOLS = [
    get_contract_details,
    get_vacancy_status,
    get_expiring_contracts,
    compare_revenue,
    get_annual_rent_roll,
    get_deposit_return_schedule,
    get_rent_per_pyung,
    get_current_rent_free_impact,
    execute_sql_query,
]
TOOL_MAP = {fn.__name__: fn for fn in TOOLS}


# ---------------------------------------------------------------------------
# 에이전트
# ---------------------------------------------------------------------------
def _find_key(d, key):
    """중첩된 설정에서 key를 찾습니다. (secrets.toml에서 키가 다른 섹션 아래에 들어간 경우 대비)"""
    try:
        if key in d:
            return d[key]
        for v in d.values():
            if hasattr(v, "keys"):
                found = _find_key(v, key)
                if found:
                    return found
    except Exception:
        pass
    return None


def get_gemini_api_key():
    try:
        found = _find_key(st.secrets, "GEMINI_API_KEY")
        if found:
            return found
    except Exception:
        pass
    import os
    import tomllib
    secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
    try:
        with open(secrets_path, "rb") as f:
            return _find_key(tomllib.load(f), "GEMINI_API_KEY")
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _get_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def _month_shift(d: date, delta: int) -> str:
    idx = d.year * 12 + (d.month - 1) + delta
    return f"{idx // 12}년 {idx % 12 + 1}월"


def _build_system_instruction() -> str:
    today = date.today()
    weekday = "월화수목금토일"[today.weekday()]
    try:
        names = _all_asset_names()
    except Exception:
        names = list(ASSET_ALIASES.keys())
    alias_lines = "\n".join(
        f"- {n}: {', '.join(ASSET_ALIASES.get(n, [])) or '(별칭 없음)'}" for n in names
    )
    return f"""당신은 부동산 자산관리 회사의 데이터 분석 어시스턴트입니다. 사내 DB를 도구로 조회해 정확하게 답합니다.

# 기준 시점
- 오늘: {today:%Y-%m-%d} ({weekday}요일)
- 이번달: {_month_shift(today, 0)}, 다음달: {_month_shift(today, 1)}, 지난달: {_month_shift(today, -1)}
- 연도 없이 월만 말하면 올해({today.year}년)로 해석합니다. '26년'은 2026년입니다.

# 자산명 (DB 영문명: 사용자가 쓰는 별칭)
{alias_lines}
- 전용 도구에는 한글 별칭을 그대로 넘겨도 됩니다. SQL을 직접 작성할 때는 반드시 영문 DB명을 쓰세요.

# 데이터 규칙
- 면적 단위는 모두 '평'입니다. 금액은 원(KRW)이며, currency='USD' 계약은 달러입니다.
- monthly_rent/monthly_maintenance_fee는 최초 계약 금액입니다. 인상·렌트프리·일할이 반영된 실제 수입은 렌트롤 도구로 계산합니다.
- 임차인·계약 조건 질문은 status='ACTIVE' 계약을 봅니다.
- '오늘 시점에 실제 점유 중인' 계약은 start_date <= 오늘 <= end_date 이면서 status IN ('ACTIVE','RENEWED')입니다.
- 공실은 물리적 공실과 모집 가능 공실(입주 예정 신규 계약 제외)을 구분해서 답합니다. 중개·마케팅 목적이면 모집 가능 공실을 기준으로 답합니다.
- NOC는 (유효 임대료 + 관리비 + 보증금×운용이율/12) / 계약면적(전체면적)입니다. 보증금 운용이율 기본값은 연 {LEASE_ASSUMPTIONS['DEPOSIT_YIELD'] * 100:.1f}%이며, 답변에 가정을 밝힙니다.
- 렌트프리 월은 rent_free_details에 JSON 배열(예: ["2026-10","2026-11"])로 저장됩니다.

# 도구 선택
- 임차인 계약 정보: get_contract_details
- 공실/공실률, 입주 예정 면적, 모집 가능 공실: get_vacancy_status
- 만기 도래 계약: get_expiring_contracts / 보증금 반환 일정: get_deposit_return_schedule
- 월별·연간 수입: get_annual_rent_roll / 기간 비교(전월, 전년, 누계, 임의 월): compare_revenue
- 평당 단가, 유효 임대료(Effective Rent), 렌트프리 할인율, NOC: get_rent_per_pyung / 특정 월 렌트프리 업체와 기회비용: get_current_rent_free_impact
- 위로 해결되지 않는 조회(임차인 목록, 조건 검색 등): execute_sql_query
- 서로 독립적인 조회가 여러 개 필요하면 한 번에 병렬로 호출하세요.
- 도구가 오류나 '찾지 못함'을 반환하면, 안내에 따라 인자나 쿼리를 고쳐 다시 시도하세요.

# 답변 작성
- 첫 문장에 질문에 대한 결론(핵심 수치, 업체명)을 바로 말합니다.
- 금액은 천 단위 콤마를 쓰고, 큰 금액은 억원/만원을 함께 적습니다.
- 3건 이상 나열할 때는 마크다운 표를 씁니다.
- 기준일, 포함 범위(예: 유효 계약만, 렌트롤 기준)를 한 줄로 밝힙니다.
- 도구 결과에 없는 수치를 만들거나 추측하지 않습니다. 데이터가 없으면 없다고 말합니다.
- 질문이 모호하면 가장 합리적인 해석으로 답하고, 어떻게 해석했는지 짧게 밝힙니다.
- 한국어로, 간결하게 답합니다.

# DB 스키마 (PostgreSQL)
{DB_SCHEMA}
"""


def _history_to_contents(chat_history, types):
    """UI의 대화 이력(list[dict] 또는 과거 호환용 문자열)을 Gemini Content 리스트로 변환."""
    if not chat_history:
        return []
    if isinstance(chat_history, str):
        return [types.Content(role="user", parts=[types.Part.from_text(text=f"[이전 대화]\n{chat_history}")]),
                types.Content(role="model", parts=[types.Part.from_text(text="이전 대화 내용을 참고하겠습니다.")])]
    contents = []
    for m in chat_history[-HISTORY_MESSAGES:]:
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=content)]))
    while contents and contents[0].role == "model":  # 대화는 user 메시지로 시작해야 함
        contents.pop(0)
    return contents


def _coerce_args(fn, args: dict) -> dict:
    """모델이 정수를 실수(10.0)로 보내는 경우 등을 보정하고, 알 수 없는 인자는 버립니다."""
    sig = inspect.signature(fn)
    out = {}
    for k, v in args.items():
        if k not in sig.parameters:
            continue
        ann = sig.parameters[k].annotation
        if v is not None and ann in (int, Optional[int]):
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                pass
        out[k] = v
    return out


def _run_tool(name: str, args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if fn is None:
        return f"알 수 없는 도구입니다: {name}"
    try:
        return str(fn(**_coerce_args(fn, args)))
    except TypeError as e:
        return f"도구 인자 오류: {e}. 도구 설명의 인자 형식에 맞춰 다시 호출하세요."
    except Exception as e:
        return f"도구 실행 중 오류: {e}"


def _clip(result: str) -> str:
    if len(result) <= MAX_RESULT_CHARS:
        return result
    return result[:MAX_RESULT_CHARS] + "\n...(결과가 길어 잘렸습니다. 조건을 좁혀 다시 조회하세요.)"


def _is_transient(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("503", "unavailable", "overloaded", "500", "internal", "deadline"))


def _is_rate_limited(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "429" in msg or "quota" in low or "resource_exhausted" in low:
        return "API 사용량 한도에 도달했습니다. 1분 정도 후에 다시 질문해 주세요."
    if _is_transient(e):
        return "Gemini 서버가 일시적으로 혼잡합니다. 잠시 후 다시 질문해 주세요."
    return f"답변 생성 중 오류가 발생했습니다: {msg[:300]}"


def _stream_with_retry(client, contents, config, retries: int = 2):
    """일시적 서버 오류와 분당 호출 한도(429)는 첫 응답 조각을 받기 전까지만 재시도합니다."""
    for attempt in range(retries + 1):
        received = False
        try:
            for chunk in client.models.generate_content_stream(
                model=MODEL_NAME, contents=contents, config=config
            ):
                received = True
                yield chunk
            return
        except Exception as e:
            if not received and attempt < retries:
                if _is_transient(e):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if _is_rate_limited(e):
                    time.sleep(5 * (attempt + 1))  # 5초, 10초 대기 후 재시도
                    continue
            raise


def stream_chat_response(user_message: str, chat_history=None):
    """답변을 스트리밍하는 제너레이터.

    yield 형식: (kind, payload)
      - ("status", 문자열): 진행 상황 (예: 도구 실행 중)
      - ("delta", 문자열): 답변 텍스트 조각
      - ("reset", None): 지금까지 출력한 텍스트를 지움 (도구 호출 전 중간 멘트였던 경우)
    """
    api_key = get_gemini_api_key()
    if not api_key:
        yield ("delta", "GEMINI_API_KEY가 설정되지 않았습니다. .streamlit/secrets.toml을 확인해 주세요.")
        return

    from google.genai import types

    client = _get_client(api_key)
    contents = _history_to_contents(chat_history, types)
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

    base_kwargs = dict(
        system_instruction=_build_system_instruction(),
        tools=TOOLS,
        temperature=0.2,
        # SDK의 자동 함수 실행을 끄고 직접 실행합니다(병렬 호출 처리, 진행 상황 표시, 한도 제어).
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        # 단순 DB 조회형 질문이 대부분이라 깊은 추론보다 응답 속도가 중요합니다.
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )
    config = types.GenerateContentConfig(**base_kwargs)
    # 마지막 라운드에서는 도구 호출을 막고 지금까지의 결과로 답하게 합니다.
    final_config = types.GenerateContentConfig(
        **base_kwargs,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
        ),
    )

    total_calls = 0
    emitted_any = False
    try:
        for round_idx in range(MAX_TOOL_ROUNDS + 1):
            cfg = final_config if round_idx == MAX_TOOL_ROUNDS else config
            parts, calls, emitted = [], [], False
            for chunk in _stream_with_retry(client, contents, cfg):
                cand = chunk.candidates[0] if chunk.candidates else None
                if not cand or not cand.content or not cand.content.parts:
                    continue
                for p in cand.content.parts:
                    parts.append(p)  # thought_signature 보존을 위해 모든 part를 그대로 보관
                    if p.function_call:
                        calls.append(p.function_call)
                    elif p.text and not p.thought:
                        emitted = emitted_any = True
                        yield ("delta", p.text)

            if not calls:
                if not emitted:
                    yield ("delta", "죄송합니다. 답변을 생성하지 못했습니다. 질문을 조금 바꿔서 다시 시도해 주세요.")
                return

            if emitted:
                yield ("reset", None)
                emitted_any = False
            contents.append(types.Content(role="model", parts=parts))

            responses = []
            for fc in calls:
                total_calls += 1
                yield ("status", f"🔎 {TOOL_LABELS.get(fc.name, fc.name)} 중...")
                if total_calls > MAX_TOOL_CALLS:
                    result = "도구 호출 한도를 초과했습니다. 지금까지 조회한 결과만으로 답변하세요."
                else:
                    result = _run_tool(fc.name, dict(fc.args or {}))
                responses.append(types.Part.from_function_response(
                    name=fc.name, response={"result": _clip(result)}
                ))
            contents.append(types.Content(role="user", parts=responses))
            yield ("status", "✍️ 답변 작성 중...")
    except Exception as e:
        if emitted_any:
            yield ("delta", f"\n\n(응답이 중단되었습니다: {_friendly_error(e)})")
        else:
            yield ("reset", None)
            yield ("delta", _friendly_error(e))


def generate_chat_response(user_message: str, chat_history=None) -> str:
    """스트리밍 없이 최종 답변 문자열만 반환합니다(테스트/호환용)."""
    answer = ""
    for kind, payload in stream_chat_response(user_message, chat_history):
        if kind == "delta":
            answer += payload
        elif kind == "reset":
            answer = ""
    return answer
