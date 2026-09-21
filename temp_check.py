import sqlite3
import pandas as pd

conn = sqlite3.connect('asset_management.db')

df_hp = pd.read_sql_query("SELECT contract_id, asset_name, floor, company_name FROM Lease_Contracts WHERE company_name LIKE '%하이파킹%'", conn)
df_hp.to_csv('hp_contracts.csv', index=False, encoding='utf-8-sig')

df_assets = pd.read_sql_query("SELECT DISTINCT asset_name FROM Asset_Area", conn)
df_assets.to_csv('assets_list.csv', index=False, encoding='utf-8-sig')
