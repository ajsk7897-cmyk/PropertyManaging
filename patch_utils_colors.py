import codecs

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

start_marker = "    def highlight_renewed_month(row):"
end_marker = "    styler = df.style.apply(highlight_total_row, axis=1)"

i_start = content.find(start_marker)
i_end = content.find(end_marker, i_start)

if i_start == -1 or i_end == -1:
    print("Block not found!")
    exit(1)

old_block = content[i_start:i_end]

new_block = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        
        rent_cols = [c for c in row.index if '월 임대료' in str(c) and str(c).replace('월 임대료', '').strip().isdigit()]
        
        for idx, col in enumerate(rent_cols):
            r_val = row[col]
            m_col = str(col).replace('임대료', '관리비')
            m_val = row[m_col] if m_col in row.index else 0
            try:
                r_float = float(str(r_val).replace(',', ''))
                m_float = float(str(m_val).replace(',', ''))
            except:
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

            try:
                col_idx = list(row.index).index(col)
                m_idx = list(row.index).index(m_col) if m_col in row.index else None
            except:
                continue

            # ① 렌트프리월: 임대료=0, 관리비>0, 이전달 임대료 있었음
            if r_float <= 0 and m_float > 0 and pr_float > 0:
                rf_style = 'background-color: #bfdbfe !important; font-weight: 700; color: #1e40af; data-tooltip: rr-rent-free'
                styles[col_idx] = rf_style
                if m_idx is not None:
                    styles[m_idx] = rf_style
                continue
            
            if r_float <= 0:
                continue

            # ② 정기인상/갱신월: 이전달 대비 임대료 변동
            if pr_float > 0 and abs(r_float - pr_float) > 1.0:
                if ppr_float > 0 and ((r_float > pr_float and pr_float > ppr_float) or (r_float < pr_float and pr_float < ppr_float)):
                    pass
                else:
                    is_mid_month = False
                    if abs(next_r_float - r_float) > 1.0 and ((next_r_float > r_float and r_float > pr_float) or (next_r_float < r_float and r_float < pr_float)):
                        is_mid_month = True
                        
                    tooltip_class = "rr-mid-month" if is_mid_month else "rr-renew"
                    style_str = f'background-color: #dcfce7 !important; font-weight: 700; color: #166534; data-tooltip: {tooltip_class}'
                    
                    styles[col_idx] = style_str
                    if m_idx is not None:
                        styles[m_idx] = style_str
        return styles

"""

content = content.replace(old_block, new_block)

# tooltip 주입 부분도 렌트프리 케이스 추가
old_tooltip = "            if tt == 'rr-mid-month':\n                title = '\U0001f4c8 \uc6d4 \uc911\uac04\uc5d0 \uc778\uc0c1 (\uc77c\ud560 \uacc4\uc0b0 \uc801\uc6a9)'\n            else:\n                title = '\U0001f504 \uacc4\uc57d \uac31\uc2e0 (\ubcc0\uacbd)'"
new_tooltip = "            if tt == 'rr-mid-month':\n                title = '\U0001f4c8 \uc6d4 \uc911\uac04\uc5d0 \uc778\uc0c1 (\uc77c\ud560 \uacc4\uc0b0 \uc801\uc6a9)'\n            elif tt == 'rr-rent-free':\n                title = '\U0001f381 \ub80c\ud2b8\ud504\ub9ac (\uc784\ub300\ub8cc \uba74\uc81c \uc6d4)'\n            else:\n                title = '\U0001f4ca \uc815\uae30 \uc778\uc0c1 / \uacc4\uc57d \uac31\uc2e0'"

content = content.replace(old_tooltip, new_tooltip)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("Done!")
