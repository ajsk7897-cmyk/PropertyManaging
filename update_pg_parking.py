import streamlit as st
import psycopg2

db_url = st.secrets["DATABASE_URL"]
conn = psycopg2.connect(db_url)
c = conn.cursor()

# 1. '주차장' 층 추가 (HQ Building(renewed 본점), Busan, Dunsan, Gwangju)
target_assets = ['HQ Building', 'Busan', 'Dunsan', 'Gwangju']
for asset in target_assets:
    c.execute("SELECT 1 FROM Asset_Area WHERE asset_name = %s AND floor = '주차장'", (asset,))
    if not c.fetchone():
        c.execute("""
            INSERT INTO Asset_Area (asset_name, floor, exclusive_area, common_area, total_area, bank_area)
            VALUES (%s, '주차장', 0.0, 0.0, 0.0, 0.0)
        """, (asset,))

# 2. 하이파킹 층수 '주차장'으로 변경 (기존 계약, 신규 계약 모두 포함)
c.execute("UPDATE Lease_Contracts SET floor = '주차장' WHERE company_name LIKE '%하이파킹%' OR company_name LIKE '%Hi%Parking%' OR company_name LIKE '%하이%파킹%'")

conn.commit()
conn.close()
print("PostgreSQL Update Complete")
