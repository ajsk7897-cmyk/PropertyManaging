import codecs
import sys

file_path = 'utils.py'
with codecs.open(file_path, 'r', 'utf-8') as f:
    content = f.read()

# 1. display_styled_table 함수 시그니처에 change_map_col 파라미터 추가
old_sig = 'def display_styled_table(df, freeze_cols=1, format_dict=None, custom_css="", height=None):'
new_sig = 'def display_styled_table(df, freeze_cols=1, format_dict=None, custom_css="", height=None, change_map_col=None):'

if old_sig in content:
    content = content.replace(old_sig, new_sig)
    print("Signature updated.")
else:
    print("Signature NOT FOUND")
    sys.exit(1)

# 2. display_styled_table 내부 highlight_renewed_month 함수를 change_map 활용 버전으로 교체
old_renew_in_styled = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        
        rent_cols = [c for c in row.index if '월 임대료' in str(c) and str(c).replace('월 임대료', '').strip().isdigit()]
        
        for idx, col in enumerate(rent_cols):
            r_val = row[col]
            m_col = str(col).replace('임대료', '관리비')
            m_val = row[m_col] if m_col in row.index else 0
            try:
                r_float = float(str(r_val).replace(',', ''))
                m_float = float(str(m_val).replace(',', ''))
            except:
                continue
            
            pr_float = 0
            if idx > 0:
                try: pr_float = float(str(row[rent_cols[idx-1]]).replace(',', ''))
                except: pass
            
            next_r_float = r_float
            if idx < len(rent_cols) - 1:
                try: next_r_float = float(str(row[rent_cols[idx+1]]).replace(',', ''))
                except: pass
            
            ppr_float = 0
            if idx > 1:
                try: ppr_float = float(str(row[rent_cols[idx-2]]).replace(',', ''))
                except: pass

            try:
                col_idx = list(row.index).index(col)
                m_idx = list(row.index).index(m_col) if m_col in row.index else None
            except:
                continue

            # ① 렌트프리월: 임대료=0, 관리비>0, 이전달 임대료 있었음
            if r_float <= 0 and m_float > 0 and pr_float > 0:
                rf_style = 'background-color: #bfdbfe !important; font-weight: 700; color: #1e40af; data-tooltip: rr-rent-free'
                styles[col_idx] = rf_style
                if m_idx is not None:
                    styles[m_idx] = rf_style
                continue
            
            if r_float <= 0:
                continue

            # ② 정기인상/갱신월: 이전달 대비 임대료 변동
            if pr_float > 0 and abs(r_float - pr_float) > 1.0:
                if ppr_float > 0 and ((r_float > pr_float and pr_float > ppr_float) or (r_float < pr_float and pr_float < ppr_float)):
                    pass
                else:
                    is_mid_month = False
                    if abs(next_r_float - r_float) > 1.0 and ((next_r_float > r_float and r_float > pr_float) or (next_r_float < r_float and r_float < pr_float)):
                        is_mid_month = True
                        
                    tooltip_class = "rr-mid-month" if is_mid_month else "rr-renew"
                    style_str = f'background-color: #dcfce7 !important; font-weight: 700; color: #166534; data-tooltip: {tooltip_class}'
                    
                    styles[col_idx] = style_str
                    if m_idx is not None:
                        styles[m_idx] = style_str
        return styles"""

new_renew_in_styled = """    def highlight_renewed_month(row):
        styles = [''] * len(row)
        if 'TOTAL' in str(row.values):
            return styles
        
        rent_cols = [c for c in row.index if '월 임대료' in str(c) and str(c).replace('월 임대료', '').strip().isdigit()]
        
        # _change_map: {월번호: 'renew'|'increase'} (데이터 생성시 주입된 메타데이터)
        c_map = {}
        if change_map_col and change_map_col in row.index:
            try:
                val = row[change_map_col]
                if isinstance(val, dict):
                    c_map = val
            except:
                pass
        
        for idx, col in enumerate(rent_cols):
            r_val = row[col]
            m_col = str(col).replace('임대료', '관리비')
            m_val = row[m_col] if m_col in row.index else 0
            try:
                r_float = float(str(r_val).replace(',', ''))
                m_float = float(str(m_val).replace(',', ''))
            except:
                continue
            
            month_num = None
            try:
                month_num = int(str(col).replace('월 임대료', '').strip())
            except:
                pass
            
            pr_float = 0
            if idx > 0:
                try: pr_float = float(str(row[rent_cols[idx-1]]).replace(',', ''))
                except: pass
            
            next_r_float = r_float
            if idx < len(rent_cols) - 1:
                try: next_r_float = float(str(row[rent_cols[idx+1]]).replace(',', ''))
                except: pass
            
            ppr_float = 0
            if idx > 1:
                try: ppr_float = float(str(row[rent_cols[idx-2]]).replace(',', ''))
                except: pass

            try:
                col_idx = list(row.index).index(col)
                m_idx = list(row.index).index(m_col) if m_col in row.index else None
            except:
                continue

            # ① 렌트프리월: 임대료=0, 관리비>0, 이전달 임대료 있었음
            if r_float <= 0 and m_float > 0 and pr_float > 0:
                rf_style = 'background-color: #bfdbfe !important; font-weight: 700; color: #1e40af; data-tooltip: rr-rent-free'
                styles[col_idx] = rf_style
                if m_idx is not None:
                    styles[m_idx] = rf_style
                continue
            
            if r_float <= 0:
                continue

            # ② 갱신/정기인상월: _change_map 우선 참조, 없으면 값 변동으로 감지
            if pr_float > 0 and abs(r_float - pr_float) > 1.0:
                if ppr_float > 0 and ((r_float > pr_float and pr_float > ppr_float) or (r_float < pr_float and pr_float < ppr_float)):
                    pass
                else:
                    is_mid_month = False
                    if abs(next_r_float - r_float) > 1.0 and ((next_r_float > r_float and r_float > pr_float) or (next_r_float < r_float and r_float < pr_float)):
                        is_mid_month = True
                    
                    # change_map으로 갱신/정기인상 구분
                    change_type = c_map.get(month_num, 'increase') if month_num else 'increase'
                    
                    if is_mid_month:
                        tooltip_class = "rr-mid-month"
                        # 월 중간 갱신이면 주황, 정기인상이면 초록
                        if change_type == 'renew':
                            style_str = f'background-color: #fed7aa !important; font-weight: 700; color: #9a3412; data-tooltip: {tooltip_class}'
                        else:
                            style_str = f'background-color: #dcfce7 !important; font-weight: 700; color: #166534; data-tooltip: {tooltip_class}'
                    elif change_type == 'renew':
                        # 갱신: 주황색 계열
                        tooltip_class = "rr-renew"
                        style_str = f'background-color: #ffedd5 !important; font-weight: 700; color: #9a3412; data-tooltip: {tooltip_class}'
                    else:
                        # 정기인상: 초록색 계열
                        tooltip_class = "rr-increase"
                        style_str = f'background-color: #dcfce7 !important; font-weight: 700; color: #166534; data-tooltip: {tooltip_class}'
                    
                    styles[col_idx] = style_str
                    if m_idx is not None:
                        styles[m_idx] = style_str
        return styles"""

if old_renew_in_styled in content:
    content = content.replace(old_renew_in_styled, new_renew_in_styled)
    print("highlight_renewed_month in display_styled_table updated.")
else:
    print("highlight block NOT FOUND")
    sys.exit(1)

# 3. tooltip 텍스트에 갱신/인상 구분 추가
old_tooltip_map = """            elif tt == 'rr-rent-free':
                title = '🎁 렌트프리 (임대료 면제 월)'
            else:
                title = '📊 정기 인상 / 계약 갱신'"""
new_tooltip_map = """            elif tt == 'rr-rent-free':
                title = '🎁 렌트프리 (임대료 면제 월)'
            elif tt == 'rr-renew':
                title = '🔄 계약 갱신'
            elif tt == 'rr-increase':
                title = '📈 정기 인상'
            else:
                title = '📈 정기 인상 / 계약 갱신'"""

content = content.replace(old_tooltip_map, new_tooltip_map)

with codecs.open(file_path, 'w', 'utf-8') as f:
    f.write(content)
print("utils.py updated successfully.")
