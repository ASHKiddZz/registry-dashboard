import sqlite3

def create_clean_db():
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()

    # Create the clean tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS Users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        role TEXT,
                        category_level TEXT,
                        password TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Modules (
                        module_id TEXT PRIMARY KEY,
                        module_name TEXT,
                        duration INTEGER,
                        lecture_hours INTEGER,
                        tutorial_hours INTEGER,
                        practical_hours INTEGER)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS Allocations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        module_id TEXT,
                        cohort TEXT DEFAULT 'Main Group',
                        FOREIGN KEY(user_id) REFERENCES Users(user_id),
                        FOREIGN KEY(module_id) REFERENCES Modules(module_id))''')

    # Spawn the master Super Admin account so they can actually log in!
    cursor.execute("SELECT * FROM Users WHERE name='Super Admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO Users (name, role, category_level, password) VALUES (?, ?, ?, ?)", 
                       ('Super Admin', 'Registry Officer', 'N/A', 'admin123'))
        
    conn.commit()
    conn.close()
    print("✅ Clean database generated! You can now log in with Username: Super Admin | Password: admin123")

if __name__ == "__main__":
    create_clean_db()