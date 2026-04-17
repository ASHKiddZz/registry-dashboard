import sqlite3

def upgrade_database():
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()
    
    try:
        # We add the new column and default existing assignments to 'Main Group'
        cursor.execute("ALTER TABLE Allocations ADD COLUMN cohort TEXT DEFAULT 'Main Group'")
        conn.commit()
        print("✅ SUCCESS: Added 'cohort' column to Allocations table!")
    except sqlite3.OperationalError as e:
        # If the column already exists, SQLite will throw an error, which we catch here
        print(f"⚠️ NOTE: Database already upgraded. ({e})")
        
    conn.close()

if __name__ == "__main__":
    upgrade_database()