import re as _re
import pandas as pd

df = pd.DataFrame({
    '자산명': ['Test'],
    '1월 임대료': [1000.0],
    '2월 임대료': [1200.0],
})

def test_highlight(row):
    styles = [''] * len(row)
    styles[1] = 'background-color: #dcfce3 !important; font-weight: 700; color: #166534; data-tooltip: rr-renew'
    return styles

styler = df.style.apply(test_highlight, axis=1)
html = styler.to_html()

id_tooltip_map = {}
for id_match, tooltip_val in _re.findall(r'#(T_[\w]+)\s*\{[^}]*data-tooltip:\s*(rr-[\w-]+)[^}]*\}', html):
    id_tooltip_map[id_match] = tooltip_val

print("ID tooltip map:", id_tooltip_map)

def _add_title_to_td(m):
    td_tag = m.group(0)
    td_id = m.group(1)
    if td_id in id_tooltip_map:
        tt = id_tooltip_map[td_id]
        if tt == 'rr-mid-month':
            title = '📈 월 중간에 인상 (일할 계산 적용)'
        else:
            title = '🔄 계약 갱신 (변경)'
        return td_tag.replace('<td ', f'<td title="{title}" ')
    return td_tag

html_out = _re.sub(r'<td id="(T_[\w]+)"', _add_title_to_td, html)
html_out = _re.sub(r'\s*data-tooltip:\s*rr-[\w-]+;', '', html_out)

m = _re.search(r'<td[^>]*title[^>]*>', html_out)
print("title 태그:", repr(m.group()) if m else "NOT FOUND")
print("data-tooltip 제거됨:", 'data-tooltip' not in html_out)
