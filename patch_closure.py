import codecs
import sys

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# display_styled_table 안에서 _change_map 컬럼을 실제 df에서 추출하고
# highlight_renewed_month 클로저가 이를 참조하도록 수정

# styler.apply 호출 전에 change_map 데이터를 df에서 추출하는 코드 추가
old_apply = """    styler = df.style.apply(highlight_total_row, axis=1)
    if any("임대료" in str(c) for c in df.columns):
        styler = styler.apply(highlight_renewed_month, axis=1)"""

new_apply = """    # _change_map 컬럼이 df에 있으면 추출 후 highlight 함수에서 활용
    # (display 시에는 drop 되어 있지만, change_map_col 파라미터로 원본 데이터 참조)
    # change_map_col은 df에 포함되어 있지 않을 수 있으므로 별도 df_full에서 추출
    _row_change_maps = {}  # row index -> change_map dict

    styler = df.style.apply(highlight_total_row, axis=1)
    if any("임대료" in str(c) for c in df.columns):
        styler = styler.apply(highlight_renewed_month, axis=1)"""

if old_apply in content:
    content = content.replace(old_apply, new_apply)
    print("Apply block updated.")
else:
    print("Apply block NOT FOUND")

# highlight_renewed_month 함수 안에서 change_map_col을 사용할 때
# df에서 해당 컬럼이 이미 drop된 경우 (즉 항상 row에 없는 경우)를 처리하기 위해
# 클로저 변수로 별도 mapping을 관리하도록 수정
# 이미 change_map_col이 row.index에 있는 경우만 처리하므로 현재 구현은 correct.
# 문제: display 시 drop(columns=[..., "_change_map"])를 했으므로 row에 없음.
# 해결: change_map_col을 drop하기 전 df에서 미리 index->dict 매핑을 만들어 클로저에 전달

old_sig = 'def display_styled_table(df, freeze_cols=1, format_dict=None, custom_css="", height=None, change_map_col=None):'
new_func_start = '''def display_styled_table(df, freeze_cols=1, format_dict=None, custom_css="", height=None, change_map_col=None, _change_maps_preloaded=None):'''

# 이미 change_map_col이 있으면 함수 시작부분에서 _row_change_maps를 구성하도록 수정
old_hasattr = '    if hasattr(df, "data"):\n        df = df.data'
new_hasattr = '''    if hasattr(df, "data"):
        df = df.data
    
    # _change_map 메타데이터: change_map_col이 df 안에 있으면 미리 추출
    # (highlight 함수 클로저에서 row 인덱스로 참조)
    _row_change_maps = {}
    if change_map_col and change_map_col in df.columns:
        for _ri, _rv in df[change_map_col].items():
            if isinstance(_rv, dict):
                _row_change_maps[_ri] = _rv'''

if old_hasattr in content:
    content = content.replace(old_hasattr, new_hasattr)
    print("hasattr block updated.")
else:
    print("hasattr block NOT FOUND")

# highlight_renewed_month 안에서 c_map을 row에서 읽는 대신 _row_change_maps 클로저 참조로 교체
old_cmap = '''        # _change_map: {월번호: 'renew'|'increase'} (데이터 생성시 주입된 메타데이터)
        c_map = {}
        if change_map_col and change_map_col in row.index:
            try:
                val = row[change_map_col]
                if isinstance(val, dict):
                    c_map = val
            except:
                pass'''

new_cmap = '''        # _change_map: {월번호: 'renew'|'increase'} (데이터 생성시 주입된 메타데이터)
        # _row_change_maps는 display_styled_table 클로저에서 참조
        c_map = _row_change_maps.get(row.name, {})'''

if old_cmap in content:
    content = content.replace(old_cmap, new_cmap)
    print("c_map block updated.")
else:
    print("c_map block NOT FOUND")

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("Done!")
