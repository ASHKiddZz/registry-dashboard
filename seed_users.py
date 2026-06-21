import pandas as pd
from sqlalchemy import create_engine

# Using your exact cloud connection string
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def seed_cloud():
    print("⏳ Connecting to Cloud...")
    engine = create_engine(CLOUD_DB_URL)
    
    # Building the perfect showcase users
    users_data = {
        "user_id": [1, 2, 3, 4],
        "username": ["registry", "hod", "alovelace", "jsmith"],
        "password": ["admin123", "admin123", "admin123", "admin123"],
        "role": ["Registry Officer", "HoD", "Lecturer", "Lecturer"],
        "name": ["Registry Admin", "Head of Department", "Ada Lovelace", "John Smith"]
    }
    
    df = pd.DataFrame(users_data)
    
    # Inject directly into the cloud!
    df.to_sql("Users", engine, if_exists="replace", index=False)
    print("✅ Core users successfully injected into the Cloud!")

if __name__ == "__main__":
    seed_cloud()