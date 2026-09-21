import codecs
import sys
import re

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# 기존 tooltip 마커 방식의 style_str을 새로운 방식(CSS 클래스 마커)으로 교체
old_tooltip_block = """                    tooltip_tag = \"/* tooltip: mid-month */\" if is_mid_month else \"/* tooltip: renew */\"
                    style_str = f'background-color: #dcfce3 !important; font-weight: 700; color: #166534; {tooltip_tag}'"""

new_tooltip_block = """                    # pandas styler는 CSS를 <style> 블록에 분리 생성하므로
                    # 인라인 style에 title 직접 주입 불가. 대신 class명을 마커로 활용한다.
                    # class 이름에 tooltip 종류를 인코딩해두고 HTML 후처리에서 title 어트리뷰트 삽입
                    tooltip_class = \"rr-mid-month\" if is_mid_month else \"rr-renew\"
                    style_str = f'background-color: #dcfce3 !important; font-weight: 700; color: #166534;'"""

if old_tooltip_block in content:
    content = content.replace(old_tooltip_block, new_tooltip_block)
    print("Tooltip style replaced.")
else:
    print("NOT FOUND: old_tooltip_block")
    sys.exit(1)

# styles[col_idx] = style_str 이후에 별도 class 마커 dict 추가
old_apply_block = """                    try:
                        col_idx = list(row.index).index(col)
                        styles[col_idx] = style_str
                        m_col = str(col).replace('임대료', '관리비')
                        if m_col in row.index:
                            m_idx = list(row.index).index(m_col)
                            styles[m_idx] = style_str
                    except:
                        pass
        return styles"""

new_apply_block = """                    try:
                        col_idx = list(row.index).index(col)
                        styles[col_idx] = style_str
                        m_col = str(col).replace('임대료', '관리비')
                        if m_col in row.index:
                            m_idx = list(row.index).index(m_col)
                            styles[m_idx] = style_str
                        # CSS 클래스를 부여하기 위해 styles에 클래스 마커 삽입
                        # Pandas styler는 style 속성만 지원하므로 클래스 마커는
                        # data-rr 속성을 style 값에 우회 삽입하여 후처리 시 활용
                        styles[col_idx] = style_str + f'; data-tooltip: {tooltip_class}'
                        if m_col in row.index:
                            styles[m_idx] = style_str + f'; data-tooltip: {tooltip_class}'
                    except:
                        pass
        return styles"""

if old_apply_block in content:
    content = content.replace(old_apply_block, new_apply_block)
    print("Apply block replaced.")
else:
    print("NOT FOUND: old_apply_block")
    sys.exit(1)

# html replace 라인: CSS 주석 방식 → data-tooltip 속성 기반 HTML 후처리 방식으로 변경
old_html_replace = """    html = styler.to_html()
    html = html.replace('/* tooltip: mid-month */\"', '\" title=\"월 중간에 인상 (일할 계산 적용)\"')
    html = html.replace('/* tooltip: renew */\"', '\" title=\"계약 갱신 (변경)\"')"""

new_html_replace = """    html = styler.to_html()
    # 'data-tooltip: rr-mid-month;' 등의 마커가 style 속성 안에 들어있음
    # 정규식으로 해당 td를 찾아 title 어트리뷰트 삽입 (브라우저 기본 툴팁)
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
    html = _re.sub(r'<td[^>]*style="([^"]*data-tooltip:[^"]*)"[^>]*>', _inject_tooltip, html)"""

if old_html_replace in content:
    content = content.replace(old_html_replace, new_html_replace)
    print("HTML replace block updated.")
else:
    print("NOT FOUND: old_html_replace")
    sys.exit(1)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("utils.py updated successfully for proper tooltip injection.")
