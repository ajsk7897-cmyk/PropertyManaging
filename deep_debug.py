import codecs
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

# 실제 td가 어떻게 생성되는지 전체 구조 확인
print("=== td 태그 샘플 ===")
matches = _re.findall(r'<td[^>]*>[^<]*</td>', html)
for m in matches:
    print(repr(m[:300]))
    
print("\n=== style 블록 in <style> ===")
style_block = _re.findall(r'<style[^>]*>.*?</style>', html, _re.DOTALL)
if style_block:
    print(repr(style_block[0][:800]))
