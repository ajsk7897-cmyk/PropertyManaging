import codecs
import sys
import re as _re

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# 현재 잘못된 HTML post-processing 로직을 올바른 것으로 교체
old_html_process = """    html = styler.to_html()
    # 'data-tooltip: rr-mid-month;' 등의 마커가 style 속성 안에 들어있음
    # 정규식으로 해당 td를 찾아 title 어트리뷰트 삽입 (브라우저 기본 툴팁)
    import re as _re
    def _inject_tooltip(m):
        tag = m.group(0)
        style_content = m.group(1)
        if 'data-tooltip: rr-mid-month' in style_content:
            clean_style = _re.sub(r';?\\s*data-tooltip:\\s*rr-mid-month', '', style_content).strip(';').strip()
            return tag.replace(style_content, clean_style).replace('<td ', '<td title="📈 월 중간에 인상 (일할 계산 적용)" ')
        elif 'data-tooltip: rr-renew' in style_content:
            clean_style = _re.sub(r';?\\s*data-tooltip:\\s*rr-renew', '', style_content).strip(';').strip()
            return tag.replace(style_content, clean_style).replace('<td ', '<td title="🔄 계약 갱신 (변경)" ')
        return tag
    html = _re.sub(r'<td[^>]*style="([^"]*data-tooltip:[^"]*)"[^>]*>', _inject_tooltip, html)"""

new_html_process = """    html = styler.to_html()
    # Pandas Styler는 <style> 블록의 #ID 선택자로 스타일을 적용함.
    # data-tooltip: rr-xxx 마커를 가진 ID를 <style>에서 찾아,
    # 해당 <td id="..."> 에 title 어트리뷰트를 직접 삽입하는 방식 사용
    import re as _re
    # 스타일 블록에서 tooltip 마커가 있는 ID들 수집
    id_tooltip_map = {}
    for id_match, tooltip_val in _re.findall(r'#(T_[\\w]+)\\s*\\{[^}]*data-tooltip:\\s*(rr-[\\w-]+)[^}]*\\}', html):
        id_tooltip_map[id_match] = tooltip_val
    # td 태그에 title 삽입
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
    html = _re.sub(r'<td id="(T_[\\w]+)"', _add_title_to_td, html)
    # 스타일 블록에서 data-tooltip 가짜 CSS 속성 제거 (잘못된 CSS 오류 방지)
    html = _re.sub(r'\\s*data-tooltip:\\s*rr-[\\w-]+;', '', html)"""

if old_html_process in content:
    content = content.replace(old_html_process, new_html_process)
    print("HTML process block replaced.")
else:
    # 이전 단순한 버전도 시도
    old2 = """    html = styler.to_html()
    html = html.replace('/* tooltip: mid-month */\"', '\" title=\"월 중간에 인상 (일할 계산 적용)\"')
    html = html.replace('/* tooltip: renew */\"', '\" title=\"계약 갱신 (변경)\"')"""
    if old2 in content:
        content = content.replace(old2, new_html_process)
        print("HTML process block replaced (alt).")
    else:
        print("NOT FOUND: html process block")
        # 현재 html = styler.to_html() 이후 구간 직접 출력
        idx = content.find("html = styler.to_html()")
        print("Context:", repr(content[idx:idx+400]))
        sys.exit(1)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("utils.py successfully updated.")    
