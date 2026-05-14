import sqlite3
import os

db_name = 'registry_database.db'

# Delete the old database if it somehow exists to ensure a completely clean slate
if os.path.exists(db_name):
    os.remove(db_name)

conn = sqlite3.connect(db_name)
cursor = conn.cursor()

print("🔨 Building Enterprise Database Schema...")

# 1. Create Users Table (With FT/PT, Departments, Category)
cursor.execute('''
CREATE TABLE Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    password TEXT DEFAULT 'password123',
    role TEXT NOT NULL,
    department TEXT DEFAULT 'Unassigned',
    employment_type TEXT DEFAULT 'FT',
    title TEXT DEFAULT '',
    hire_year INTEGER DEFAULT 2020,
    category_level TEXT DEFAULT 'Category 5 (Other Academic)'
)
''')

# 2. Create Modules Table (With Programme, Coordinator, Weightage, and Hours)
cursor.execute('''
CREATE TABLE Modules (
    module_id TEXT PRIMARY KEY,
    module_name TEXT NOT NULL,
    duration INTEGER DEFAULT 15,
    lecture_hours INTEGER DEFAULT 3,
    tutorial_hours INTEGER DEFAULT 0,
    practical_hours INTEGER DEFAULT 0,
    programme TEXT DEFAULT 'General',
    weightage REAL DEFAULT 0.0,
    programme_coordinator TEXT DEFAULT 'Unassigned'
)
''')

# 3. Create Allocations Table (With Cohort, Semester, Students)
cursor.execute('''
CREATE TABLE Allocations (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    module_id TEXT,
    cohort TEXT DEFAULT 'Group A',
    semester TEXT DEFAULT 'Semester 1',
    level_semester TEXT DEFAULT 'L1S1',
    students_count INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES Users(user_id),
    FOREIGN KEY(module_id) REFERENCES Modules(module_id)
)
''')

# 4. Create Pending Promotions Table (With PDF BLOB Support)
cursor.execute('''
CREATE TABLE Pending_Promotions (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    proposed_role TEXT,
    proposed_category TEXT,
    status TEXT DEFAULT 'Pending Registry',
    rejection_reason TEXT DEFAULT '',
    registration_letter BLOB,
    FOREIGN KEY(user_id) REFERENCES Users(user_id)
)
''')

print("💉 Injecting Realistic University Data...")

# --- SEED USERS ---
users_data = [
    (1, "Admin Officer", "Registry Officer", "Registry", "FT", "Mr.", 2015, "Admin"),
    (2, "Prof. Alan Turing", "HoS", "Computer Science", "FT", "Prof.", 2010, "Category 1 (Management)"),
    (3, "Dr. Grace Hopper", "HoD", "Software Engineering", "FT", "Dr.", 2012, "Category 2 (Professional)"),
    (4, "Dr. John von Neumann", "Professor", "Mathematics", "FT", "Dr.", 2015, "Category 3 (Technical)"),
    (5, "Larry Lecturer", "Lecturer", "Computer Science", "FT", "Mr.", 2021, "Category 5 (Other Academic)"),
    (6, "Ada Lovelace", "Senior Lecturer", "Software Engineering", "PT", "Ms.", 2018, "Category 4 (PhD Staff)")
]
cursor.executemany("INSERT INTO Users (user_id, name, role, department, employment_type, title, hire_year, category_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", users_data)

# --- SEED MODULES ---
modules_data = [
    ("CS101", "Intro to Programming", 15, 3, 1, 2, "BSc Computer Science", 4.0, "Prof. Alan Turing"),
    ("CS102", "Data Structures", 15, 3, 1, 2, "BSc Computer Science", 4.0, "Prof. Alan Turing"),
    ("SE201", "Software Engineering Concepts", 15, 3, 0, 0, "BSc Software Eng", 3.0, "Dr. Grace Hopper"),
    ("SE202", "Agile Methodologies", 12, 2, 1, 0, "BSc Software Eng", 3.0, "Dr. Grace Hopper"),
    ("MTH101", "Calculus I", 15, 4, 1, 0, "BSc Mathematics", 5.0, "Dr. John von Neumann"),
    ("NET301", "Network Security", 15, 3, 0, 3, "BSc Computer Science", 4.5, "Dr. Grace Hopper")
]
cursor.executemany("INSERT INTO Modules (module_id, module_name, duration, lecture_hours, tutorial_hours, practical_hours, programme, weightage, programme_coordinator) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", modules_data)

# --- SEED ALLOCATIONS (Creating real workloads!) ---
allocations_data = [
    # Larry Lecturer (Normal Workload)
    (5, "CS101", "Group A", "Semester 1", "L1S1", 45),
    (5, "CS101", "Group B", "Semester 1", "L1S1", 42),
    (5, "CS102", "Group A", "Semester 2", "L1S2", 40),
    # Ada Lovelace (Overloaded Part-Time Staff for Tab 3 Testing)
    (6, "SE201", "Group A", "Semester 1", "L2S1", 30),
    (6, "SE201", "Group B", "Semester 1", "L2S1", 35),
    (6, "SE202", "Group A", "Semester 1", "L2S1", 30),
    (6, "NET301", "Group A", "Semester 1", "L3S1", 25),
    (6, "NET301", "Group B", "Semester 1", "L3S1", 22),
    (6, "SE202", "Group A", "Semester 2", "L2S2", 28),
    # John von Neumann (Math Dept)
    (4, "MTH101", "Group A", "Semester 1", "L1S1", 60),
    (4, "MTH101", "Group B", "Semester 2", "L1S2", 55),
]
cursor.executemany("INSERT INTO Allocations (user_id, module_id, cohort, semester, level_semester, students_count) VALUES (?, ?, ?, ?, ?, ?)", allocations_data)

conn.commit()
conn.close()

print("✅ SUCCESS! 'registry_database.db' has been created perfectly.")
print("🚀 You can now run 'streamlit run app.py' to test the full system!")