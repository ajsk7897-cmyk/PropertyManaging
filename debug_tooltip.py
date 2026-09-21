import codecs
import re

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# Pandas Styler.to_html() 이 생성하는 실제 td 태그 형식을 확인한 뒤
# title 어트리뷰트 삽입 방식을 검증하는 테스트
import pandas as pd

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
    # 마킹 테스트 
    tooltip_tag = "/* tooltip: renew */"
    style_str = f'background-color: #dcfce3 !important; font-weight: 700; color: #166534; {tooltip_tag}'
    styles[4] = style_str  # 2월 임대료
    return styles

styler = df.style.apply(test_highlight, axis=1)
html = styler.to_html()

# 실제 생성된 HTML에서 tooltip 마크 주변 컨텍스트 확인
idx = html.find('tooltip')
print("===CONTEXT AROUND tooltip MARKER===")
if idx != -1:
    print(repr(html[max(0,idx-80):idx+80]))
else:
    print("NOT FOUND!")

# td 태그 전체 컨텍스트 확인
print("\n===SAMPLE TD TAG===")
m = re.search(r'<td[^>]*background-color: #dcfce3[^>]*>.*?</td>', html)
if m:
    print(repr(m.group()))
else:
    print("NOT FOUND!")
    # Find any td with style
    m2 = re.search(r'<td[^>]*style="[^"]*"[^>]*>.*?</td>', html)
    if m2:
        print("sample td:", repr(m2.group()[:200]))
