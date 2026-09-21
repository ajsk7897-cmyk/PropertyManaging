import codecs
import sys

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

target1_start = "    def highlight_renewed_month(row):"
target1_end = "    if auto_format:"
idx_start = content.find(target1_start)
idx_end = content.find(target1_end, idx_start)

if idx_start == -1 or idx_end == -1:
    print("Target 1 not found")
    sys.exit(1)

target1_original = content[idx_start:idx_end]

replacement1 = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        
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

            if pr_float > 0 and abs(r_float - pr_float) > 1.0:
                # 3달 연속으로 변동(주로 단조증가/감소)이 있으면 이번달은 두번째 인상달이므로 하이라이트 패스
                if ppr_float > 0 and ((r_float > pr_float and pr_float > ppr_float) or (r_float < pr_float and pr_float < ppr_float)):
                    pass 
                else:
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

    styler = df.style.apply(highlight_total_row, axis=1)
    if any("임대료" in str(c) for c in df.columns):
        styler = styler.apply(highlight_renewed_month, axis=1)
"""
content = content.replace(target1_original, replacement1)

target2 = """    uid = "tbl_" + uuid.uuid4().hex[:8]
    html = styler.to_html()"""

replacement2 = """    uid = "tbl_" + uuid.uuid4().hex[:8]
    html = styler.to_html()
    html = html.replace('/* tooltip: mid-month */"', '" title="월 중간에 인상 (일할 계산 적용)"')
    html = html.replace('/* tooltip: renew */"', '" title="계약 변경 (갱신)"')"""

if target2 in content:
    content = content.replace(target2, replacement2)
    print("Target 2 replaced")
else:
    print("Target 2 not found")
    sys.exit(1)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("utils.py successfully updated for tooltip logic.")
