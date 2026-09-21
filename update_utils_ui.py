import codecs

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

target = "    styler = df.style.apply(highlight_total_row, axis=1)"
replacement = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        prev_r = None
        prev_m = None
        cols = list(row.index)
        for i, col in enumerate(cols):
            col_str = str(col)
            if '월 임대료' in col_str and col_str.replace('월 임대료', '').strip().isdigit():
                r_val = row[col]
                m_col = col_str.replace('임대료', '관리비')
                m_val = row[m_col] if m_col in cols else 0
                if prev_r is not None and prev_r > 0:
                    try:
                        r_float = float(str(r_val).replace(',', ''))
                        pr_float = float(str(prev_r).replace(',', ''))
                        m_float = float(str(m_val).replace(',', ''))
                        pm_float = float(str(prev_m).replace(',', ''))
                        if (abs(r_float - pr_float) > 1.0 or abs(m_float - pm_float) > 1.0) and r_float > 0:
                            # 갱신(증액/감액) 된 월에 부드러운 그린 톤 하이라이트 부여
                            styles[i] = 'background-color: #dcfce3 !important; font-weight: 700; color: #166534;'
                            if m_col in cols:
                                m_idx = cols.index(m_col)
                                styles[m_idx] = 'background-color: #dcfce3 !important; font-weight: 700; color: #166534;'
                    except:
                        pass
                if str(r_val).strip() != '' and str(r_val).strip() != 'nan':
                    try:
                        r_float = float(str(r_val).replace(',', ''))
                        if r_float > 0:
                            prev_r = r_val
                            prev_m = m_val
                    except:
                        pass
        return styles

    styler = df.style.apply(highlight_total_row, axis=1)
    if any("임대료" in str(c) for c in df.columns):
        styler = styler.apply(highlight_renewed_month, axis=1)"""

if target in content:
    content = content.replace(target, replacement)
    with codecs.open(file_path, 'w', 'utf-8') as f:
        f.write(content)
    print("utils.py updated successfully.")
else:
    print("Target string not found in utils.py.")
