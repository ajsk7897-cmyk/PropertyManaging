import sqlite3
import os
import json
import pandas as pd

DB_FILE = "asset_management.db"

def main():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    try:
        # Check if RentRoll_Overrides table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='RentRoll_Overrides'")
        if not c.fetchone():
            print("No RentRoll_Overrides table found. No migration needed.")
            return

        c.execute("SELECT * FROM RentRoll_Overrides")
        overrides = c.fetchall()

        if not overrides:
            print("RentRoll_Overrides is empty. No migration needed.")
            return

        print(f"Found {len(overrides)} override records. Processing...")
        
        # Load all contracts to get the exact un-truncated rent schedules
        c.execute("SELECT contract_id, rent_schedule, monthly_rent, monthly_maintenance_fee, currency FROM Lease_Contracts")
        contracts = c.fetchall()
        
        contract_dict = {}
        for row in contracts:
            contract_dict[row[0]] = {
                "rent_schedule": row[1],
                "monthly_rent": float(row[2] or 0),
                "monthly_maintenance_fee": float(row[3] or 0),
                "currency": row[4] or "KRW"
            }

        updates_made = 0
        deletes_made = 0

        for ov in overrides:
            cid = ov[0]
            year = ov[1]
            month = ov[2]
            over_rent = ov[3]
            over_maint = ov[4]

            if cid not in contract_dict:
                continue

            c_info = contract_dict[cid]
            
            # Reconstruct the target date for the override
            # Day doesn't matter for fetching scheduled amount, use 1st of the month
            target_date_str = f"{year}-{month:02d}-01"
            target_date = pd.to_datetime(target_date_str)
            
            rent_schedule_json = c_info["rent_schedule"]
            default_rent = c_info["monthly_rent"]
            default_maint = c_info["monthly_maintenance_fee"]
            
            exact_rent = default_rent
            exact_maint = default_maint
            
            # Mimic get_scheduled_amount logic
            if rent_schedule_json:
                try:
                    schedule = json.loads(rent_schedule_json)
                    for period in schedule:
                        s_date = pd.to_datetime(period["start_date"]).date()
                        e_date = pd.to_datetime(period["end_date"]).date()
                        if target_date.date() < s_date and exact_rent == default_rent:
                            break
                        if s_date <= target_date.date() <= e_date:
                            exact_rent = float(period.get("rent", default_rent))
                            exact_maint = float(period.get("maint", default_maint))
                            break
                except:
                    pass

            # Calculate truncated version
            truncated_rent = int(exact_rent // 10) * 10 if c_info["currency"] == "KRW" else round(exact_rent, 2)
            truncated_maint = int(exact_maint // 10) * 10 if c_info["currency"] == "KRW" else round(exact_maint, 2)
            
            # If the override matches the exact value, it's already correct.
            if over_rent == exact_rent and over_maint == exact_maint:
                continue
                
            # If the override matches the truncated value, we can safely delete it or update it to the exact value.
            # Usually, if it matches the calculated (but truncated) value, the override is redundant.
            if over_rent == truncated_rent and over_maint == truncated_maint:
                # We can delete it so the system uses the exact calculated value
                c.execute("DELETE FROM RentRoll_Overrides WHERE contract_id=? AND year=? AND month=?", (cid, year, month))
                deletes_made += 1
            else:
                pass # The user manually entered a totally different value, leave it alone.

        conn.commit()
        print(f"Migration complete: {deletes_made} redundant truncated overrides deleted, {updates_made} records updated.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
