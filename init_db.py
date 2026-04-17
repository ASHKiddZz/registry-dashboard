import sqlite3

def create_database():
    # Connect to the database (this creates the file if it doesn't exist)
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()

    # 1. Create Users Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        category_level TEXT,
        password TEXT NOT NULL
    )
    ''')

    # 2. Create Modules Table
    # The module_id will be the code from your pictures (e.g., 'SE101')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Modules (
        module_id TEXT PRIMARY KEY,
        module_name TEXT NOT NULL,
        duration INTEGER,
        lecture_hours INTEGER DEFAULT 0,
        tutorial_hours INTEGER DEFAULT 0,
        practical_hours INTEGER DEFAULT 0
    )
    ''')

    # 3. Create Allocations Table (The Bridge)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Allocations (
        allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        module_id TEXT,
        approval_status TEXT DEFAULT 'Pending HOD',
        lecturer_remarks TEXT,
        external_uni_flag BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES Users(user_id),
        FOREIGN KEY (module_id) REFERENCES Modules(module_id)
    )
    ''')

    # Inject a dummy Registry Officer account so you can log in later to test
    cursor.execute('''
    INSERT OR IGNORE INTO Users (user_id, name, role, category_level, password)
    VALUES (1, 'Super Admin', 'Registry Officer', 'N/A', 'admin123')
    ''')

    # Save and close
    conn.commit()
    conn.close()
    
    print("Success: 'registry_database.db' has been created with all tables!")

if __name__ == '__main__':
    create_database()