import os
import json
import streamlit as st
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List, Optional

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

def setup_gemini():
    """Gemini API 설정 초기화"""
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 secrets.toml에 설정되지 않았습니다. 앱을 재시작해주세요.")
    
    # 환경변수에 강제 세팅 (Streamlit 캐싱 및 구글 하위 라이브러리 충돌 방지)
    import os
    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GOOGLE_API_KEY"] = api_key
    
    genai.configure(api_key=api_key)

class RentSchedule(BaseModel):
    start_date: str = Field(description="YYYY-MM-DD 형식의 시작일")
    end_date: str = Field(description="YYYY-MM-DD 형식의 종료일")
    rent: int = Field(description="해당 기간의 월 임대료")
    maint: int = Field(description="해당 기간의 월 관리비")

class ContractExtractionResult(BaseModel):
    company_name: str = Field(description="임차인(업체명)")
    contract_date: str = Field(description="계약 체결일 (YYYY-MM-DD)")
    start_date: str = Field(description="임대 시작일 (YYYY-MM-DD)")
    end_date: str = Field(description="임대 종료일 (YYYY-MM-DD)")
    deposit: int = Field(description="보증금 총액 (숫자만, 단위 제외)")
    monthly_rent: int = Field(description="현재 기준 월 임대료 (숫자만, 단위 제외)")
    monthly_maintenance_fee: int = Field(description="현재 기준 월 관리비 (숫자만, 단위 제외)")
    contract_area: float = Field(description="임대 총면적(평수 기준, 숫자만)")
    exclusive_area: float = Field(description="전용 면적(평수 기준, 숫자만). 모르면 0.0")
    currency: str = Field(description="통화 단위 (KRW 또는 USD, 기본값 KRW)")
    rent_schedule: List[RentSchedule] = Field(description="기간별 임대료/관리비 변동 스케줄 내역. 변동이 없으면 전체 기간에 대해 1개 항목만 작성.")
    rent_free_months: List[str] = Field(description="렌트프리가 적용되는 월들의 목록. 'YYYY-MM' 형식의 문자열 리스트. 없으면 빈 리스트.")
    remarks: str = Field(description="납부 주기(예: 분기납), 인상 조건, 위약벌, 기타 계약상 특별히 명시된 특약사항이나 특이사항 종합. 없으면 빈 문자열")

def extract_contract_info(uploaded_file) -> Optional[dict]:
    """업로드된 파일(PDF/Image)에서 계약 정보를 추출합니다."""
    setup_gemini()
    
    try:
        # File API 대신 Inline Data 방식을 사용하여 Discovery API 에러(AQ. 키 포맷 에러) 원천 차단
        file_name = uploaded_file.name.lower()
        
        if file_name.endswith(".docx"):
            import docx
            import io
            doc = docx.Document(io.BytesIO(uploaded_file.getvalue()))
            text_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
            file_data = {
                "mime_type": "text/plain",
                "data": text_content.encode("utf-8")
            }
        else:
            mime_type = uploaded_file.type
            if not mime_type:
                # 기본값 설정
                if file_name.endswith(".pdf"):
                    mime_type = "application/pdf"
                elif file_name.endswith((".jpg", ".jpeg")):
                    mime_type = "image/jpeg"
                elif file_name.endswith(".png"):
                    mime_type = "image/png"
                else:
                    mime_type = "application/pdf"

            file_data = {
                "mime_type": mime_type,
                "data": uploaded_file.getvalue()
            }
        
        def call_gemini_with_fallback(inputs, generation_config):
            model_flash = genai.GenerativeModel('gemini-2.5-flash')
            model_lite = genai.GenerativeModel('gemini-3.5-flash-lite')
            try:
                return model_flash.generate_content(inputs, generation_config=generation_config)
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    return model_lite.generate_content(inputs, generation_config=generation_config)
                raise e
        
        prompt = """
        당신은 부동산 자산관리 전문가입니다. 주어진 계약서 문서를 주의 깊게 읽고, 다음의 임대차 계약 정보를 정확하게 추출해 주세요.
        
        반드시 JSON 형식으로 응답해야 하며, 제공된 JSON 스키마를 엄격히 준수하세요.
        - 면적 단위가 제곱미터(㎡)인 경우, 3.3058로 나누어 '평' 단위로 변환해 주세요.
        - 날짜는 'YYYY-MM-DD' 형식이어야 합니다.
        - 금액은 순수 숫자(integer/float)로 작성해 주세요. (원, $, 콤마 등 제거)
        - 통화는 KRW 또는 USD 중 하나를 선택하세요.
        - rent_schedule은 계약 기간 중 임대료나 관리비가 변동되는 내역을 담습니다. 변동이 없더라도 최초 전체 기간에 대한 내역을 최소 1개 작성하세요.
        - rent_free_months는 렌트프리(무상임대, Rent Free, 면제기간) 기간이 있을 경우, 해당 기간에 포함되는 모든 월을 'YYYY-MM' 형식의 리스트로 추출하세요.
          예를 들어 "임대 개시일로부터 3개월 렌트프리"이고 시작일이 2025-01-01이면 ["2025-01", "2025-02", "2025-03"]으로 작성합니다.
          "렌트프리 없음"이거나 명시되어 있지 않으면 빈 리스트 []를 반환하세요. 절대 null이 아닌 빈 리스트여야 합니다.
        - remarks(비고)에는 임대료 납부 방식(예: 선납, 월납, 분기납 등), 인상률 합의, 연체 요율, 중도해지 위약금 등 계약상 주요 특약사항을 모두 요약해서 넣어주세요.
        """
        
        response = call_gemini_with_fallback(
            [file_data, prompt],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ContractExtractionResult,
                temperature=0.0
            )
        )
        
        # 결과 파싱
        if response.text:
            return json.loads(response.text)
        return None
        
    except Exception as e:
        st.error(f"AI 추출 중 오류가 발생했습니다: {e}")
        return None
