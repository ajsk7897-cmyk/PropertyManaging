import codecs
import re
import pandas as pd

file_path = 'utils.py'

# 검증: 실제 td에 title이 삽입되는지 테스트
df = pd.DataFrame({
    '자산명': ['Test'],
    '층': ['1F'],
    '업체명': ['ABC'],
    '통화': ['KRW'],
    '1월 임대료': [1000.0],
    '1월 관리비': [500.0],
    '2월 임대료': [1200.0],
    '2월 관리비': [500.0],
})

def test_highlight(row):
    styles = [''] * len(row)
    tooltip_class = 'rr-renew'
    style_str = 'background-color: #dcfce3 !important; font-weight: 700; color: #166534;'
    styles[4] = style_str + f'; data-tooltip: {tooltip_class}'
    return styles

styler = df.style.apply(test_highlight, axis=1)
html = styler.to_html()

import re as _re
def _inject_tooltip(m):
    tag = m.group(0)
    style_content = m.group(1)
    if 'data-tooltip: rr-mid-month' in style_content:
        clean_style = _re.sub(r';?\s*data-tooltip:\s*rr-mid-month', '', style_content).strip(';').strip()
        return tag.replace(style_content, clean_style).replace('<td ', '<td title="📈 월 중간에 인상 (일할 계산 적용)" ')
    elif 'data-tooltip: rr-renew' in style_content:
        clean_style = _re.sub(r';?\s*data-tooltip:\s*rr-renew', '', style_content).strip(';').strip()
        return tag.replace(style_content, clean_style).replace('<td ', '<td title="🔄 계약 갱신 (변경)" ')
    return tag
html_out = _re.sub(r'<td[^>]*style="([^"]*data-tooltip:[^"]*)"[^>]*>', _inject_tooltip, html)

print("=== title 삽입 검증 ===")
m = _re.search(r'<td[^>]*title[^>]*>', html_out)
print("title 태그 발견:", repr(m.group()) if m else "NOT FOUND")
print("data-tooltip 제거됨:", 'data-tooltip' not in html_out)
