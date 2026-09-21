import re as _re
import pandas as pd

# 실제 상황과 동일하게 _row_change_maps가 채워지고 tooltip이 삽입되는지 검증
df = pd.DataFrame({
    '자산명': ['Test'],
    '층': ['1F'],
    '업체명': ['ABC'],
    '통화': ['KRW'],
    '1월 임대료': [1000.0],
    '1월 관리비': [500.0],
    '2월 임대료': [1300.0],
    '2월 관리비': [500.0],
    '_change_map': [{2: 'increase'}],
})

_row_change_maps = {}
if '_change_map' in df.columns:
    for _ri, _rv in df['_change_map'].items():
        if isinstance(_rv, dict):
            _row_change_maps[_ri] = _rv
    df = df.drop(columns=['_change_map'], errors='ignore')

print("_row_change_maps:", _row_change_maps)

def highlight_fn(row):
    styles = [''] * len(row)
    c_map = _row_change_maps.get(row.name, {})
    rent_cols = [c for c in row.index if '월 임대료' in str(c) and str(c).replace('월 임대료','').strip().isdigit()]
    for idx, col in enumerate(rent_cols):
        try:
            r_float = float(str(row[col]).replace(',',''))
            pr_float = float(str(row[rent_cols[idx-1]]).replace(',','')) if idx > 0 else 0
        except:
            continue
        if pr_float > 0 and abs(r_float - pr_float) > 1.0:
            try: month_num = int(str(col).replace('월 임대료','').strip())
            except: month_num = None
            change_type = c_map.get(month_num, 'increase') if month_num else 'increase'
            tooltip_class = 'rr-increase' if change_type == 'increase' else 'rr-renew'
            style_str = f'background-color: #dcfce7; data-tooltip: {tooltip_class}'
            col_idx = list(row.index).index(col)
            styles[col_idx] = style_str
    return styles

styler = df.style.apply(highlight_fn, axis=1)
html = styler.to_html()

# id_tooltip_map 추출
id_tooltip_map = {}
for id_match, tooltip_val in _re.findall(r'#(T_[\w]+)\s*\{[^}]*data-tooltip:\s*(rr-[\w-]+)[^}]*\}', html):
    id_tooltip_map[id_match] = tooltip_val

print("id_tooltip_map:", id_tooltip_map)

# td에 title 삽입
def _add_title_to_td(m):
    td_tag = m.group(0)
    td_id = m.group(1)
    if td_id in id_tooltip_map:
        return td_tag.replace('<td ', f'<td title="TEST-OK" ')
    return td_tag

html_out = _re.sub(r'<td id="(T_[\w]+)"', _add_title_to_td, html)

m = _re.search(r'<td[^>]*title="TEST-OK"[^>]*>', html_out)
print("title 삽입 성공:", bool(m))
if m:
    print("태그:", repr(m.group()))
print("data-tooltip 남아있음:", 'data-tooltip' in html_out)
