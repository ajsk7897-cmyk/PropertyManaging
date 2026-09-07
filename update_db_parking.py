import sqlite3

db_path = 'asset_management.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. '주차장' 층 추가 (HQ Building(renewed 본점), Busan, Dunsan, Gwangju)
target_assets = ['HQ Building', 'Busan', 'Dunsan', 'Gwangju']
for asset in target_assets:
    c.execute("SELECT 1 FROM Asset_Area WHERE asset_name = ? AND floor = '주차장'", (asset,))
    if not c.fetchone():
        c.execute("""
            INSERT INTO Asset_Area (asset_name, floor, exclusive_area, common_area, total_area, bank_area)
            VALUES (?, '주차장', 0.0, 0.0, 0.0, 0.0)
        """, (asset,))

# 2. 하이파킹 층수 '주차장'으로 변경
c.execute("UPDATE Lease_Contracts SET floor = '주차장' WHERE company_name LIKE '%하이파킹%' OR company_name LIKE '%Hi%Parking%' OR company_name LIKE '%하이%파킹%'")

conn.commit()
conn.close()
print("DB Update Complete")
