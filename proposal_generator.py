import io
import math
import datetime
from openpyxl import load_workbook
import os

def py_to_sqm(py):
    if not py: return ""
    return math.floor(float(py) * 3.3058 * 100) / 100

def py_to_sf(py):
    if not py: return ""
    return math.floor(float(py) * 35.5832 * 100) / 100

def safe_str(val):
    if val is None or str(val).strip() == "" or str(val).lower() == "none":
        return ""
    return str(val)

def generate_renewal_proposal(old_data, new_data, comps_list=None):
    template_path = '기안파일/Lease_Renewal_Proposal.xlsx'
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"템플릿 파일이 존재하지 않습니다: {template_path}")
        
    wb = load_workbook(template_path)
    
    def set_value(ws_name, cell, value):
        if ws_name in wb.sheetnames:
            if value is None or str(value).lower() == "none":
                value = ""
            ws = wb[ws_name]
            try:
                ws[cell].value = value
            except AttributeError:
                # 'MergedCell' object attribute 'value' is read-only 에러 처리
                for merged_range in ws.merged_cells.ranges:
                    if cell in merged_range:
                        top_left = merged_range.coord.split(':')[0]
                        ws[top_left].value = value
                        break

    def format_money(val):
        if val is None or str(val).strip() == "":
            return ""
        try:
            return f"{int(val):,}"
        except (ValueError, TypeError):
            return val

    old_gross_py = float(old_data.get('기존_총임대면적_평') or 0)
    old_exc_py = float(old_data.get('기존_전용면적_평') or 0)
    
    new_gross_py = float(new_data.get('신규_총임대면적_평') or 0)
    new_exc_py = float(new_data.get('신규_전용면적_평') or 0)

    # 가. '임대갱신품의서' 시트
    set_value('임대갱신품의서', 'D6', safe_str(new_data.get('자산주소')))
    set_value('임대갱신품의서', 'K6', safe_str(new_data.get('GPMS_ID')))
    set_value('임대갱신품의서', 'D7', safe_str(new_data.get('임차인명')))
    set_value('임대갱신품의서', 'K7', safe_str(new_data.get('부동산사용목적')))
    set_value('임대갱신품의서', 'D8', safe_str(new_data.get('대리인명')))
    set_value('임대갱신품의서', 'K8', safe_str(new_data.get('임대층')))

    set_value('임대갱신품의서', 'D11', old_gross_py if old_gross_py else "")
    set_value('임대갱신품의서', 'K11', old_exc_py if old_exc_py else "")
    set_value('임대갱신품의서', 'D12', py_to_sqm(old_gross_py) if old_gross_py else "")
    set_value('임대갱신품의서', 'K12', py_to_sqm(old_exc_py) if old_exc_py else "")
    set_value('임대갱신품의서', 'D13', py_to_sf(old_gross_py) if old_gross_py else "")
    set_value('임대갱신품의서', 'K13', py_to_sf(old_exc_py) if old_exc_py else "")
    
    old_rent = int(old_data.get('기존_월임대료') or 0)
    old_maint = int(old_data.get('기존_월관리비') or 0)
    old_dep = int(old_data.get('기존_보증금') or 0)
    new_rent = int(new_data.get('갱신_월임대료') or 0)
    new_maint = int(new_data.get('갱신_월관리비') or 0)
    new_dep = int(new_data.get('갱신_보증금') or 0)

    set_value('임대갱신품의서', 'D14', format_money(old_rent))
    set_value('임대갱신품의서', 'K14', format_money(old_maint))
    set_value('임대갱신품의서', 'D15', format_money(old_dep))

    # [신규] 갱신 임대 조건 영역 (Streamlit 폼 입력 변수 덮어쓰기)
    new_start_str = safe_str(new_data.get('갱신_임대시작일'))
    new_end_str = safe_str(new_data.get('갱신_임대만료일'))
    
    # User explicitly requested D17, D18
    set_value('임대갱신품의서', 'D17', new_end_str)
    set_value('임대갱신품의서', 'D18', new_start_str)
    
    # Also overwrite the other cells found in the template under Renewal Proposal
    set_value('임대갱신품의서', 'D19', new_gross_py if new_gross_py else "")
    set_value('임대갱신품의서', 'J18', new_exc_py if new_exc_py else "")
    set_value('임대갱신품의서', 'J19', format_money(new_maint))
    set_value('임대갱신품의서', 'D20', format_money(new_rent))
    set_value('임대갱신품의서', 'D21', format_money(new_dep))
    set_value('임대갱신품의서', 'J21', new_end_str)
    set_value('임대갱신품의서', 'D22', new_start_str)

    # C34 : 작업대산 계약이 속한 자산의 건물 전체의 평균 평당 관리비 (해당자산 모든 계약별 평당관리비의 합/계약 수)
    total_maint_per_py = 0
    count_contracts = 0
    
    if old_gross_py > 0:
        total_maint_per_py += (old_maint / old_gross_py)
        count_contracts += 1
        
    if comps_list:
        for comp in comps_list:
            comp_area = float(comp.get('contract_area') or 0)
            if comp_area > 0:
                comp_maint = float(comp.get('monthly_maintenance_fee') or 0)
                total_maint_per_py += (comp_maint / comp_area)
                count_contracts += 1
                
    avg_maint_per_py = total_maint_per_py / count_contracts if count_contracts > 0 else 0
    set_value('임대갱신품의서', 'C34', format_money(int(avg_maint_per_py)))

    # A38 : 지정된 텍스트 입력
    a38_text = """[계약 명]

1. 협의 History
1) 협의 이슈사항
 -  진행

2) 임대차 조건
 -   
-> 보증금 : 
  -> 임대료 : 
  -> 관리비 : 
  -> Rent-Free : 
  -> 계약기간 : 

2. 결론
 - """
    set_value('임대갱신품의서', 'A38', a38_text)

    # 나. '비교표' 시트
    set_value('비교표', 'D4', py_to_sf(old_exc_py) if old_exc_py else "")
    set_value('비교표', 'G4', "좌동" if old_exc_py == new_exc_py else py_to_sf(new_exc_py))
    
    set_value('비교표', 'D5', py_to_sf(old_gross_py) if old_gross_py else "")
    set_value('비교표', 'G5', "좌동" if old_gross_py == new_gross_py else py_to_sf(new_gross_py))
    
    set_value('비교표', 'D6', safe_str(new_data.get('임차인명')))
    set_value('비교표', 'G6', "좌동")
    
    set_value('비교표', 'D7', format_money(old_dep))
    set_value('비교표', 'G7', "좌동" if old_dep == new_dep else format_money(new_dep))
    set_value('비교표', 'K7', safe_str(new_data.get('보증금비고')))
    
    rent_inc_str = ""
    if old_rent > 0 and old_rent != new_rent:
        inc_pct = ((new_rent - old_rent) / old_rent) * 100
        rent_inc_str = f"{inc_pct:.1f}% 인상" if inc_pct > 0 else f"{abs(inc_pct):.1f}% 인하"
        
    set_value('비교표', 'D8', format_money(old_rent))
    set_value('비교표', 'G8', "좌동" if old_rent == new_rent else format_money(new_rent))
    set_value('비교표', 'K8', rent_inc_str if rent_inc_str else safe_str(new_data.get('임대료비고')))
    
    maint_inc_str = ""
    if old_maint > 0 and old_maint != new_maint:
        inc_pct = ((new_maint - old_maint) / old_maint) * 100
        maint_inc_str = f"{inc_pct:.1f}% 인상" if inc_pct > 0 else f"{abs(inc_pct):.1f}% 인하"
        
    set_value('비교표', 'D9', format_money(old_maint))
    set_value('비교표', 'G9', "좌동" if old_maint == new_maint else format_money(new_maint))
    set_value('비교표', 'K9', maint_inc_str if maint_inc_str else safe_str(new_data.get('관리비비고')))
    
    old_term = safe_str(old_data.get('기존_임대차기간'))
    new_term = safe_str(new_data.get('갱신_임대차기간'))
    set_value('비교표', 'D10', old_term)
    set_value('비교표', 'G10', "좌동" if old_term == new_term else new_term)
    set_value('비교표', 'K10', "계약갱신")

    # [비교 사례(Comps) 자동 추출 및 매핑 로직]
    if comps_list and len(comps_list) > 0 and new_gross_py > 0:
        target_rent_per_py = new_rent / new_gross_py
        
        comps_sorted = []
        for comp in comps_list:
            comp_area = float(comp.get('contract_area', 0))
            if comp_area <= 0: continue
            comp_rent = float(comp.get('monthly_rent', 0))
            comp_rent_per_py = comp_rent / comp_area
            diff = abs(comp_rent_per_py - target_rent_per_py)
            comps_sorted.append((diff, comp_rent_per_py, comp))
            
        comps_sorted.sort(key=lambda x: x[0])
        top_3_comps = comps_sorted[:3]
        
        # ※ 실제 템플릿의 열 위치에 맞게 알파벳 및 행 좌표는 유연하게 지정
        cols = ['E', 'F', 'G']
        row_floor = 13     # 예: 층수
        row_dep_py = 14    # 예: 평당 보증금
        row_rent_py = 15   # 예: 평당 임대료
        row_maint_py = 16  # 예: 평당 관리비
        
        for idx, (diff, rent_per_py, comp) in enumerate(top_3_comps):
            if idx >= 3: break
            col = cols[idx]
            comp_area = float(comp.get('contract_area', 1))
            dep_per_py = float(comp.get('deposit', 0)) / comp_area
            maint_per_py = float(comp.get('monthly_maintenance_fee', 0)) / comp_area
            
            set_value('비교표', f'{col}{row_floor}', safe_str(comp.get('floor')))
            set_value('비교표', f'{col}{row_dep_py}', format_money(int(dep_per_py)))
            set_value('비교표', f'{col}{row_rent_py}', format_money(int(rent_per_py)))
            set_value('비교표', f'{col}{row_maint_py}', format_money(int(maint_per_py)))

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    company_name = safe_str(new_data.get('임차인명'))
    if not company_name:
        company_name = "임차인"
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    filename = f"DOA_{company_name}-{today_str}.xlsx"
    
    return output.getvalue(), filename
