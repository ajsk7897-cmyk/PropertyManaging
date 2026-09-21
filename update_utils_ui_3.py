import codecs
import sys

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

target2 = "html = styler.to_html()"
replacement2 = """html = styler.to_html()
    html = html.replace('/* tooltip: mid-month */"', '" title="월 중간에 인상 (일할 계산 적용)"')
    html = html.replace('/* tooltip: renew */"', '" title="계약 갱신 (변경)"')"""

if target2 in content:
    content = content.replace(target2, replacement2)
    print("Target 2 replaced")
else:
    print("Target 2 not found")
    sys.exit(1)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("utils.py successfully updated for tooltip logic.")
