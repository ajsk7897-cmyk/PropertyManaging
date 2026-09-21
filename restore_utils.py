import codecs, sys, re

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# 망가진 590~612줄 구간 복원
# 현재: except 이후 바로 orphaned indented block (display_styled_table 함수 몸체가 끊김)
# 찾아서 제거: "    except:\r\n        return str(x)\r\n\r\n            if pd.api..."
old_broken = """    except:\r\n        return str(x)\r\n\r\n            if pd.api.types.is_numeric_dtype(df[col]):\r\n                auto_format[col] = \"{:,.2f}\"\r\n        elif any(\r\n            k in col_str\r\n            for k in [\r\n                \"금액\",\r\n                \"보증금\",\r\n                \"임대료\",\r\n                \"관리비\",\r\n                \"수익\",\r\n                \"비용\",\r\n                \"단가\",\r\n                \"NOC\",\r\n                \"월임대료\",\r\n                \"월관리비\",\r\n                \"합계\",\r\n            ]\r\n        ):\r\n            if pd.api.types.is_numeric_dtype(df[col]):\r\n                auto_format[col] = format_money"""

new_fixed = """    except:
        return str(x)

# Helper function to display styled table as HTML with scrolling
def display_styled_table(df, freeze_cols=1, format_dict=None, custom_css="", height=None, change_map_col=None):
    import uuid
    import streamlit.components.v1 as components

    if hasattr(df, "data"):
        df = df.data

    # _change_map 메타데이터: change_map_col이 df 안에 있으면 미리 추출
    _row_change_maps = {}
    if change_map_col and change_map_col in df.columns:
        for _ri, _rv in df[change_map_col].items():
            if isinstance(_rv, dict):
                _row_change_maps[_ri] = _rv
        df = df.drop(columns=[change_map_col], errors="ignore")

    auto_format = {}
    for col in df.columns:
        col_str = str(col)
        if any(k in col_str for k in ["면적", "비율", "율", "비중", "수익률"]):
            if pd.api.types.is_numeric_dtype(df[col]):
                auto_format[col] = "{:,.2f}"
        elif any(
            k in col_str
            for k in [
                "금액",
                "보증금",
                "임대료",
                "관리비",
                "수익",
                "비용",
                "단가",
                "NOC",
                "월임대료",
                "월관리비",
                "합계",
            ]
        ):
            if pd.api.types.is_numeric_dtype(df[col]):
                auto_format[col] = format_money"""

if old_broken in content:
    content = content.replace(old_broken, new_fixed)
    print("Broken block restored.")
else:
    # 다른 인코딩으로 시도
    old_broken2 = "    except:\n        return str(x)\n\n            if pd.api.types.is_numeric_dtype(df[col]):\n                auto_format[col] = \"{:,.2f}\"\n        elif any(\n            k in col_str\n            for k in [\n                \"금액\",\n                \"보증금\",\n                \"임대료\",\n                \"관리비\",\n                \"수익\",\n                \"비용\",\n                \"단가\",\n                \"NOC\",\n                \"월임대료\",\n                \"월관리비\",\n                \"합계\",\n            ]\n        ):\n            if pd.api.types.is_numeric_dtype(df[col]):\n                auto_format[col] = format_money"
    new_fixed2 = new_fixed.replace('\r\n', '\n')
    if old_broken2 in content:
        content = content.replace(old_broken2, new_fixed2)
        print("Broken block restored (LF).")
    else:
        print("ERROR: could not find broken block")
        print(repr(content[content.find("return str(x)"):content.find("return str(x)")+400]))
        sys.exit(1)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("Done!")
