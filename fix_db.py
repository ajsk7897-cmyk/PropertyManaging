import datetime
from sqlalchemy import text
from 모듈화.utils import get_engine

eng = get_engine()
with eng.begin() as conn:
    res = conn.execute(text("SELECT contract_id, start_date, end_date, status FROM Lease_Contracts WHERE company_name LIKE '%하이파킹%'")).fetchall()
    print("Before:", res)
    
    active = [r for r in res if r.status == 'ACTIVE']
    non_active = [r for r in res if r.status != 'ACTIVE']
    
    if active and non_active:
        # Assuming there is one main active renewed contract
        new_start = active[0].start_date
        new_start_date = datetime.datetime.strptime(str(new_start).split(" ")[0], "%Y-%m-%d")
        new_end_date = (new_start_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        for old in non_active:
            conn.execute(
                text("UPDATE Lease_Contracts SET end_date = :new_end WHERE contract_id = :cid"),
                {"new_end": new_end_date, "cid": old.contract_id}
            )
            print(f"Updated contract {old.contract_id} end_date to {new_end_date}")
            
    res = conn.execute(text("SELECT contract_id, start_date, end_date, status FROM Lease_Contracts WHERE company_name LIKE '%하이파킹%'")).fetchall()
    print("After:", res)
