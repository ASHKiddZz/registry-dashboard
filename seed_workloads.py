import pandas as pd
from sqlalchemy import create_engine

# Your exact cloud connection string
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def seed_workloads():
    print("⏳ Connecting to Cloud Database...")
    engine = create_engine(CLOUD_DB_URL)

    # 1. Creating 3 realistic university modules with ALL required columns
    modules_data = {
        "module_code": ["CS101", "CS102", "ENG201"],
        "module_name": ["Intro to Programming", "Data Structures", "Technical Writing"],
        "credits": [3, 4, 3],
        "department": ["Computer Science", "Computer Science", "English"],
        "tutorial_hours": [1, 2, 0],
        "practical_hours": [2, 2, 0],
        "programme": ["BSc CS", "BSc CS", "General"],
        "weightage": [1.0, 1.2, 1.0],
        "programme_coordinator": ["jsmith", "jsmith", "alovelace"]
    }
    df_mod = pd.DataFrame(modules_data)
    
    # 2. Assigning these exact modules to Larry Lecturer (user_id = 3)
    allocations_data = {
        "allocation_id": [1, 2, 3],
        "user_id": [3, 3, 3], 
        "module_code": ["CS101", "CS102", "ENG201"],
        "semester": ["Semester 1", "Semester 1", "Semester 1"],
        "level_semester": ["L1S1", "L1S1", "L2S1"],
        "students_count": [50, 45, 60]
    }
    df_alloc = pd.DataFrame(allocations_data)

    print("📦 Pushing perfectly formatted Modules...")
    # This automatically creates the "Modules" table with perfect column names
    df_mod.to_sql("Modules", engine, if_exists="replace", index=False)
    
    print("📦 Pushing Allocations assigned to Larry...")
    df_alloc.to_sql("Allocations", engine, if_exists="replace", index=False)

    print("✅ BOOM! Modules and Allocations injected and permanently linked!")

if __name__ == "__main__":
    seed_workloads()