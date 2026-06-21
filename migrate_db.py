import sqlite3
import pandas as pd
from sqlalchemy import create_engine

# --- PASTE YOUR SUPABASE CONNECTION STRING HERE ---
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def migrate_to_cloud():
    print("⏳ Connecting to local SQLite database...")
    local_conn = sqlite3.connect('registry_database.db')
    
    print("⏳ Connecting to Cloud PostgreSQL database...")
    # This creates the secure bridge to Supabase
    cloud_engine = create_engine(CLOUD_DB_URL)
    
    # Get a list of all tables currently in your local SQLite database
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", local_conn)
    table_names = tables['name'].tolist()
    
    for table in table_names:
        if table == "sqlite_sequence": # We skip this internal SQLite file
            continue
            
        print(f"📦 Migrating table: {table}...")
        
        # 1. Read the table from the local database
        df = pd.read_sql_query(f"SELECT * FROM {table}", local_conn)
        
        # 2. Write the table to the cloud database
        df.to_sql(table, cloud_engine, if_exists='replace', index=False)
        print(f"   ✅ {len(df)} rows securely moved to the cloud!")
        
    print("\n🎉 MIGRATION COMPLETE! Your data is now permanently online.")

if __name__ == "__main__":
    migrate_to_cloud()