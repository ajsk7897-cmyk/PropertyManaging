import io
import math
import datetime
from openpyxl import load_workbook
from openpyxl.styles import Border, Side, PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
import os
from copy import copy

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

def copy_cell_style(source_cell, target_cell):
    target_cell.font = copy(source_cell.font) if source_cell.font else None
    target_cell.border = copy(source_cell.border) if source_cell.border else None
    target_cell.fill = copy(source_cell.fill) if source_cell.fill else None
    target_cell.number_format = source_cell.number_format
    target_cell.protection = copy(source_cell.protection) if source_cell.protection else None
    target_cell.alignment = copy(source_cell.alignment) if source_cell.alignment else None

def generate_renewal_proposal(old_data, new_data, comps_list=None):
    template_path = '기안파일/Lease_Renewal_Proposal.xlsx'
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"템플릿 파일이 존재하지 않습니다: {template_path}")
        
    wb = load_workbook(template_path)
    
    def set_value(ws_name, cell, value, num_format=None):
        if isinstance(ws_name, int):
            try:
                ws = wb.worksheets[ws_name]
            except IndexError:
                return
        elif ws_name in wb.sheetnames:
            ws = wb[ws_name]
        else:
            return
            
        if value is None or str(value).lower() == "none":
            value = ""
        target_cell = None
        try:
            ws[cell].value = value
            target_cell = ws[cell]
        except AttributeError:
            for merged_range in ws.merged_cells.ranges:
                if cell in merged_range:
                    top_left = merged_range.coord.split(':')[0]
                    ws[top_left].value = value
                    target_cell = ws[top_left]
                    break
        if target_cell and num_format:
            target_cell.number_format = num_format

    def get_money(val):
        if val is None or str(val).strip() == "" or str(val).lower() == "none":
            return 0
        try:
            return math.floor(float(val) / 10) * 10
        except (ValueError, TypeError):
            return 0

    old_gross_py = float(old_data.get('기존_총임대면적_평') or 0)
    old_exc_py = float(old_data.get('기존_전용면적_평') or 0)
    
    new_gross_py = float(new_data.get('신규_총임대면적_평') or 0)
    new_exc_py = float(new_data.get('신규_전용면적_평') or 0)

    # Date parsing logic for calculation
    new_start_str = safe_str(new_data.get('갱신_임대시작일'))
    new_end_str = safe_str(new_data.get('갱신_임대만료일'))
    
    dt_start = None
    dt_end = None
    renewal_months = 0
    try:
        dt_start = datetime.datetime.strptime(new_start_str, "%Y-%m-%d").date()
        dt_end = datetime.datetime.strptime(new_end_str, "%Y-%m-%d").date()
        renewal_months = math.floor((dt_end - dt_start).days / 365 * 12)
    except Exception:
        pass

    # 가. '임대갱신품의서' 시트
    set_value(0, 'D6', safe_str(new_data.get('자산주소')))
    set_value(0, 'K6', safe_str(new_data.get('GPMS_ID')))
    set_value(0, 'D7', safe_str(new_data.get('임차인명')))
    set_value(0, 'K7', safe_str(new_data.get('부동산사용목적')))
    set_value(0, 'D8', safe_str(new_data.get('대리인명')))
    set_value(0, 'K8', safe_str(new_data.get('임대층')))

    set_value(0, 'D11', old_gross_py if old_gross_py else "", num_format='#,##0.00')
    set_value(0, 'K11', old_exc_py if old_exc_py else "", num_format='#,##0.00')
    set_value(0, 'D12', py_to_sqm(old_gross_py) if old_gross_py else "", num_format='#,##0.00')
    set_value(0, 'K12', py_to_sqm(old_exc_py) if old_exc_py else "", num_format='#,##0.00')
    set_value(0, 'D13', py_to_sf(old_gross_py) if old_gross_py else "", num_format='#,##0.00')
    set_value(0, 'K13', py_to_sf(old_exc_py) if old_exc_py else "", num_format='#,##0.00')
    
    old_rent = get_money(old_data.get('기존_월임대료'))
    old_maint = get_money(old_data.get('기존_월관리비'))
    old_dep = get_money(old_data.get('기존_보증금'))
    new_rent = get_money(new_data.get('갱신_월임대료'))
    new_maint = get_money(new_data.get('갱신_월관리비'))
    new_dep = get_money(new_data.get('갱신_보증금'))

    set_value(0, 'D14', old_rent, num_format='#,##0')
    set_value(0, 'J14', old_maint, num_format='#,##0')
    set_value(0, 'D15', old_dep, num_format='#,##0')

    # [수정 1] 계약 개월 수 (절사된 정수)
    set_value(0, 'D18', f"{renewal_months}개월" if renewal_months > 0 else "")

    # [수정 2] Date 포맷 변경 (엑셀 서식)
    ws_ren = wb['임대갱신품의서']
    if dt_end:
        set_value(0, 'D17', dt_end, num_format='[$-en-US]dd-mmm-yyyy;@')
        set_value(0, 'J21', dt_end, num_format='[$-en-US]dd-mmm-yyyy;@')
    else:
        set_value(0, 'D17', new_end_str)
        set_value(0, 'J21', new_end_str)

    if dt_start:
        set_value(0, 'D22', dt_start, num_format='[$-en-US]dd-mmm-yyyy;@')
    else:
        set_value(0, 'D22', new_start_str)

    set_value(0, 'D19', new_gross_py if new_gross_py else "", num_format='#,##0.00')
    set_value(0, 'J18', new_exc_py if new_exc_py else "", num_format='#,##0.00')
    set_value(0, 'J19', new_maint, num_format='#,##0')
    set_value(0, 'D20', new_rent, num_format='#,##0')
    set_value(0, 'D21', new_dep, num_format='#,##0')

    set_value(0, 'A17', '▲ Renewal Proposal 갱신 조건')

    # [수정 3] 고정 재무 지표 수식 적용 (D25, J25, G27)
    set_value(0, 'J22', '=(D21*J20)/12+D20+J19', num_format='#,##0')
    set_value(0, 'D25', '=(D15*J20)+(D14*12)+(J14*12)', num_format='#,##0')
    set_value(0, 'J25', '=(D21*J20)+(D20*12)+(J19*12)', num_format='#,##0')
    set_value(0, 'G26', '=J25/D25-1', num_format='0.0%')
    set_value(0, 'G27', '=(D21*J20)/2+(D20*6)+(J19*6)', num_format='#,##0')

    # C34 : 작업대산 계약이 속한 자산의 건물 전체의 평균 평당 관리비
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
    set_value(0, 'C34', get_money(avg_maint_per_py), num_format='#,##0')

    # A38 : 지정된 텍스트 입력
    a38_text = f"""[계약 명]

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
    set_value(0, 'A38', a38_text)

    # 나. '비교표' 시트
    set_value(1, 'A2', safe_str(new_data.get('임차인명')))
    set_value(1, 'J10', f"{renewal_months}개월" if renewal_months > 0 else "")

    set_value(1, 'D4', py_to_sf(old_exc_py) if old_exc_py else "", num_format='#,##0.00')
    set_value(1, 'G4', "좌동" if old_exc_py == new_exc_py else py_to_sf(new_exc_py), num_format=None if old_exc_py == new_exc_py else '#,##0.00')
    
    set_value(1, 'D5', py_to_sf(old_gross_py) if old_gross_py else "", num_format='#,##0.00')
    set_value(1, 'G5', "좌동" if old_gross_py == new_gross_py else py_to_sf(new_gross_py), num_format=None if old_gross_py == new_gross_py else '#,##0.00')
    
    set_value(1, 'D6', safe_str(new_data.get('임차인명')))
    set_value(1, 'G6', "좌동")
    
    set_value(1, 'D7', old_dep, num_format='#,##0')
    set_value(1, 'G7', "좌동" if old_dep == new_dep else new_dep, num_format=None if old_dep == new_dep else '#,##0')
    set_value(1, 'K7', safe_str(new_data.get('보증금비고')))
    
    rent_inc_str = ""
    if old_rent > 0 and old_rent != new_rent:
        inc_pct = ((new_rent - old_rent) / old_rent) * 100
        rent_inc_str = f"{inc_pct:.1f}% 인상" if inc_pct > 0 else f"{abs(inc_pct):.1f}% 인하"
        
    set_value(1, 'D8', old_rent, num_format='#,##0')
    set_value(1, 'G8', "좌동" if old_rent == new_rent else new_rent, num_format=None if old_rent == new_rent else '#,##0')
    set_value(1, 'K8', rent_inc_str if rent_inc_str else safe_str(new_data.get('임대료비고')))
    
    maint_inc_str = ""
    if old_maint > 0 and old_maint != new_maint:
        inc_pct = ((new_maint - old_maint) / old_maint) * 100
        maint_inc_str = f"{inc_pct:.1f}% 인상" if inc_pct > 0 else f"{abs(inc_pct):.1f}% 인하"
        
    set_value(1, 'D9', old_maint, num_format='#,##0')
    set_value(1, 'G9', "좌동" if old_maint == new_maint else new_maint, num_format=None if old_maint == new_maint else '#,##0')
    set_value(1, 'K9', maint_inc_str if maint_inc_str else safe_str(new_data.get('관리비비고')))
    
    old_term = safe_str(old_data.get('기존_임대차기간'))
    new_term = safe_str(new_data.get('갱신_임대차기간'))
    set_value(1, 'D10', old_term)
    set_value(1, 'G10', "좌동" if old_term == new_term else new_term)
    set_value(1, 'K10', "계약갱신")

    # [수정 4, 5] 비교표 연차별 스텝업 동적 렌더링
    ws_comp = wb['비교표']
    step_ups = new_data.get('step_ups', [])
    years = max(2, math.ceil(renewal_months / 12) if renewal_months > 0 else 2)
    
    # Base columns for 1st, 2nd year: D=4, G=7 (spacing is 3)
    start_col_idx = 4
    col_spacing = 3

    for y in range(1, years + 1):
        target_col_idx = start_col_idx + (y - 1) * col_spacing
        target_col = get_column_letter(target_col_idx)
        
        # Determine values
        if y <= len(step_ups):
            y_rent = int(step_ups[y-1].get('rent') or new_rent)
            y_maint = int(step_ups[y-1].get('maint') or new_maint)
        else:
            y_rent = new_rent
            y_maint = new_maint
            
        y_rent_annual = y_rent * 12
        y_maint_annual = y_maint * 12

        # Write text and values
        set_value(1, f"{target_col}13", f"{y}년 차")
        set_value(1, f"{target_col}14", new_dep, num_format='#,##0')
        set_value(1, f"{target_col}15", y_rent_annual, num_format='#,##0')
        set_value(1, f"{target_col}16", y_maint_annual, num_format='#,##0')
        set_value(1, f"{target_col}17", f"={target_col}14*임대갱신품의서!J20", num_format='#,##0')
        set_value(1, f"{target_col}18", f"=SUM({target_col}15:{target_col}17)", num_format='#,##0')
        
        # If y > 2, we must copy styles from 2nd year (col G)
        if y > 2:
            src_col = "G"
            # 13행부터 18행까지 서식 복사, 병합도 해야하지만 단순화를 위해 각 셀 서식 복사
            for row in range(13, 19):
                src_cell = ws_comp[f"{src_col}{row}"]
                tgt_cell = ws_comp[f"{target_col}{row}"]
                copy_cell_style(src_cell, tgt_cell)

    # Move Total Column (J열 로직) to the right
    total_col_idx = start_col_idx + years * col_spacing
    total_col = get_column_letter(total_col_idx)
    
    # 13행~18행 합계 서식 그리기
    for row in range(13, 19):
        # 기존 J열 서식을 복사 (J열 = 10)
        src_cell = ws_comp[f"J{row}"]
        tgt_cell = ws_comp[f"{total_col}{row}"]
        copy_cell_style(src_cell, tgt_cell)
            
        if row == 13:
            set_value(1, f"{total_col}{row}", "합계(원)")
        elif row == 14:
            set_value(1, f"{total_col}{row}", "") # 보증금 공란
        else:
            # SUM range: D15:M15 (for 3 years)
            end_sum_col = get_column_letter(total_col_idx - col_spacing)
            set_value(1, f"{total_col}{row}", f"=SUM(D{row}:{end_sum_col}{row})", num_format='#,##0')

    # [비교 사례(Comps) 평단가 자동 추출] - 부가세 제외, 총 임대면적 기준
    # C30: 작업 중인 테넌트 명
    set_value(0, 'C30', safe_str(new_data.get('임차인명')))
    # C31 ~ C35 계산
    if new_gross_py > 0:
        set_value(0, 'C31', new_dep / new_gross_py, num_format='#,##0')
        set_value(0, 'C32', new_rent / new_gross_py, num_format='#,##0')
        set_value(0, 'C33', new_maint / new_gross_py, num_format='#,##0')
        set_value(0, 'C35', (new_rent * 100 + new_dep) / new_gross_py, num_format='#,##0')
        
    for col in ['E', 'F', 'G', 'H', 'I', 'J']:
        set_value(0, f'{col}35', "")

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
        
        cols = ['E', 'F', 'G']
        row_floor = 13     
        row_dep_py = 14    
        row_rent_py = 15   
        row_maint_py = 16  
        
        for idx, (diff, rent_per_py, comp) in enumerate(top_3_comps):
            if idx >= 3: break
            col = cols[idx]
            comp_area = float(comp.get('contract_area', 1))
            dep_per_py = float(comp.get('deposit', 0)) / comp_area
            maint_per_py = float(comp.get('monthly_maintenance_fee', 0)) / comp_area
            
            set_value('비교표', f'{col}{row_floor}', safe_str(comp.get('floor')))
            set_value('비교표', f'{col}{row_dep_py}', get_money(dep_per_py), num_format='#,##0')
            set_value('비교표', f'{col}{row_rent_py}', get_money(rent_per_py), num_format='#,##0')
            set_value('비교표', f'{col}{row_maint_py}', get_money(maint_per_py), num_format='#,##0')

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    company_name = safe_str(new_data.get('임차인명'))
    if not company_name:
        company_name = "임차인"
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    filename = f"DOA_{company_name}-{today_str}.xlsx"
    
    return output.getvalue(), filename
