import sqlite3
import pandas as pd
from sqlalchemy import create_engine

# Your exact cloud connection string
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def fix_and_migrate():
    print("⏳ Connecting to the REAL local database on your tower...")
    
    # Make sure 'registry_database.db' (or whatever your real local file is named) is in this folder!
    local_conn = sqlite3.connect('registry_database.db') 
    cloud_engine = create_engine(CLOUD_DB_URL)
    
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", local_conn)
    table_names = tables['name'].tolist()
    
    for table in table_names:
        if table == "sqlite_sequence": 
            continue
            
        print(f"📦 Fixing and pushing table: {table}...")
        df = pd.read_sql_query(f"SELECT * FROM {table}", local_conn)
        
        # THE MAGIC FIX: .lower() forces PostgreSQL to play nice with your old code!
        df.to_sql(table.lower(), cloud_engine, if_exists='replace', index=False)
        print(f"   ✅ {len(df)} real rows securely moved to the cloud!")
        
    print("\n🎉 REAL DATA MIGRATED AND FIXED!")

if __name__ == "__main__":
    fix_and_migrate()