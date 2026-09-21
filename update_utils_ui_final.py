import codecs
import sys

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

start_str = "    def highlight_renewed_month(row):"
end_str = "    styler = df.style.apply(highlight_total_row, axis=1)"

idx_start = content.find(start_str)
idx_end = content.find(end_str, idx_start)

if idx_start == -1 or idx_end == -1:
    print("Failed to find target block")
    sys.exit(1)

original_block = content[idx_start:idx_end]

new_block = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        
        # 월별 임대료 컬럼 찾기 (숫자 오름차순으로 정렬되도록 주의 - 이미 데이터프레임 순서가 1~12월 순서임)
        rent_cols = [c for c in row.index if '월 임대료' in str(c) and str(c).replace('월 임대료', '').strip().isdigit()]
        
        for idx, col in enumerate(rent_cols):
            r_val = row[col]
            try:
                r_float = float(str(r_val).replace(',', ''))
            except:
                continue
            
            if r_float <= 0:
                continue
                
            pr_float = 0
            if idx > 0:
                try: pr_float = float(str(row[rent_cols[idx-1]]).replace(',', ''))
                except: pass
            
            next_r_float = r_float
            if idx < len(rent_cols) - 1:
                try: next_r_float = float(str(row[rent_cols[idx+1]]).replace(',', ''))
                except: pass
            
            ppr_float = 0
            if idx > 1:
                try: ppr_float = float(str(row[rent_cols[idx-2]]).replace(',', ''))
                except: pass

            # 이전달 값이 존재하고 변동이 일어났을 경우
            if pr_float > 0 and abs(r_float - pr_float) > 1.0:
                # 1. 만약 두 달 연속 올랐다면 (일할계산의 두번째 달) -> 하이라이트 패스!
                if ppr_float > 0 and ((r_float > pr_float and pr_float > ppr_float) or (r_float < pr_float and pr_float < ppr_float)):
                    pass 
                else:
                    # 2. 첫 번째 변동 달 (일반 인상이거나 일할계산 첫 달)
                    is_mid_month = False
                    if abs(next_r_float - r_float) > 1.0 and ((next_r_float > r_float and r_float > pr_float) or (next_r_float < r_float and r_float < pr_float)):
                        is_mid_month = True
                        
                    tooltip_tag = "/* tooltip: mid-month */" if is_mid_month else "/* tooltip: renew */"
                    style_str = f'background-color: #dcfce3 !important; font-weight: 700; color: #166534; {tooltip_tag}'
                    
                    try:
                        col_idx = list(row.index).index(col)
                        styles[col_idx] = style_str
                        m_col = str(col).replace('임대료', '관리비')
                        if m_col in row.index:
                            m_idx = list(row.index).index(m_col)
                            styles[m_idx] = style_str
                    except:
                        pass
        return styles

"""

content = content.replace(original_block, new_block)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("Target 1 logic successfully replaced.")
