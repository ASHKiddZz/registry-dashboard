from sqlalchemy import create_engine, text

# Your exact cloud connection string
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

def repair_database():
    print("⏳ Connecting to Cloud Database...")
    engine = create_engine(CLOUD_DB_URL)
    
    with engine.begin() as conn:
        # 1. Restore missing columns to Users
        conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS category_level TEXT DEFAULT \'N/A\';'))
        conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS hire_year INTEGER DEFAULT 2024;'))
        conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS department TEXT DEFAULT \'Unassigned\';'))
        conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS employment_type TEXT DEFAULT \'FT\';'))
        conn.execute(text('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS title TEXT DEFAULT \'\';'))

        # 2. Bulletproof the Modules and Allocations tables just in case they were truncated
        conn.execute(text('ALTER TABLE "Modules" ADD COLUMN IF NOT EXISTS tutorial_hours INTEGER DEFAULT 0;'))
        conn.execute(text('ALTER TABLE "Modules" ADD COLUMN IF NOT EXISTS practical_hours INTEGER DEFAULT 0;'))
        conn.execute(text('ALTER TABLE "Modules" ADD COLUMN IF NOT EXISTS programme TEXT DEFAULT \'General\';'))
        conn.execute(text('ALTER TABLE "Modules" ADD COLUMN IF NOT EXISTS weightage REAL DEFAULT 0;'))
        conn.execute(text('ALTER TABLE "Modules" ADD COLUMN IF NOT EXISTS programme_coordinator TEXT DEFAULT \'Unassigned\';'))
        
        conn.execute(text('ALTER TABLE "Allocations" ADD COLUMN IF NOT EXISTS semester TEXT DEFAULT \'Semester 1\';'))
        conn.execute(text('ALTER TABLE "Allocations" ADD COLUMN IF NOT EXISTS level_semester TEXT DEFAULT \'\';'))
        conn.execute(text('ALTER TABLE "Allocations" ADD COLUMN IF NOT EXISTS students_count INTEGER DEFAULT 0;'))

        # 3. Fix the Strict Typing crash by dropping and cleanly recreating the empty tracking tables
        conn.execute(text('DROP TABLE IF EXISTS "Lecturer_Remarks";'))
        conn.execute(text('''
            CREATE TABLE "Lecturer_Remarks" (
                remark_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                remark_text TEXT,
                status TEXT DEFAULT 'Unread',
                submit_date DATE DEFAULT CURRENT_DATE
            );
        '''))

        conn.execute(text('DROP TABLE IF EXISTS "Pending_Promotions";'))
        conn.execute(text('''
            CREATE TABLE "Pending_Promotions" (
                ticket_id SERIAL PRIMARY KEY,
                user_id BIGINT,
                proposed_role TEXT,
                proposed_category TEXT,
                status TEXT DEFAULT 'Pending HoD',
                request_date DATE DEFAULT CURRENT_DATE,
                rejection_reason TEXT,
                registration_letter BYTEA
            );
        '''))
        
    print("✅ Enterprise Schema Repaired and Bulletproofed!")

if __name__ == "__main__":
    repair_database()