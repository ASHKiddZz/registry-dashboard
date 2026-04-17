import pandas as pd
import sqlite3
import re

def import_and_anonymize():
    print("Starting the Great Import...")
    
    file_name = "annex1.csv"
    
    # --- 1. AUTO-DETECT HEADER ROW ---
    # Instead of guessing how many rows to skip, we scan the file to find the true header
    header_index = 0
    try:
        with open(file_name, 'r', encoding='latin1') as f:
            for i, line in enumerate(f):
                # We look for a row that clearly has our table titles
                if "Module Code" in line and "Resource" in line:
                    header_index = i
                    break
    except FileNotFoundError:
        print(f"Error: Could not find '{file_name}'. Make sure it is in the correct folder!")
        return

    print(f"--> Found the true table headers at row {header_index}. Reading data...")

    # --- 2. LOAD DATA ---
    # Now we pass our perfectly calculated row index!
    df = pd.read_csv(file_name, skiprows=header_index, encoding='latin1', engine='python', on_bad_lines='skip')

    # --- 3. BULLETPROOF COLUMN FINDER ---
    def get_col(keyword):
        for col in df.columns:
            if keyword.lower() in str(col).lower():
                return col
        return None

    # We use very simple keywords so it doesn't get confused by hidden spaces or line breaks
    col_resource = get_col('Resource')
    col_mod_code = get_col('Module Code')
    col_mod_title = get_col('Module Title')
    col_duration = get_col('Duration')
    col_ltp = get_col('L + T/P')

    # --- SAFETY CHECK ---
    # If it still can't find them, it will tell us EXACTLY what columns it sees
    if not col_resource or not col_mod_code:
        print("\nCRITICAL ERROR: Could not find the required columns.")
        print("Here are the columns Pandas actually found on that row:")
        print(df.columns.tolist())
        return

    # --- 4. DATABASE SETUP ---
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM Allocations")
    cursor.execute("DELETE FROM Modules")
    cursor.execute("DELETE FROM Users WHERE user_id != 1")

    # --- 5. EXTRACT AND ANONYMIZE USERS ---
    real_names = df[col_resource].dropna().unique()
    name_map = {} 
    
    for index, real_name in enumerate(real_names):
        fake_name = f"Lecturer {index + 1}"
        name_map[real_name] = fake_name
        
        cursor.execute('''
            INSERT INTO Users (name, role, category_level, password)
            VALUES (?, 'Lecturer', 'All Other Staff', 'pass123')
        ''', (fake_name,))

    # --- 6. EXTRACT MODULES AND ALLOCATIONS ---
    for index, row in df.iterrows():
        mod_code = str(row[col_mod_code]).strip()
        
        if mod_code == 'nan' or not mod_code:
            continue
            
        mod_name = str(row[col_mod_title]).strip() if col_mod_title else "Unknown"
        
        duration = 15
        if col_duration:
            duration_str = str(row[col_duration])
            duration = 12 if '12' in duration_str else 15
        
        l_hrs, t_hrs, p_hrs = 0, 0, 0
        if col_ltp:
            ltp = str(row[col_ltp]).strip()
            if '+' in ltp:
                parts = ltp.split('+')
                try:
                    l_hrs = int(re.search(r'\d+', parts[0]).group())
                    p_hrs = int(re.search(r'\d+', parts[1]).group())
                except:
                    pass
            elif ltp.isdigit():
                l_hrs = int(ltp)
            
        cursor.execute('''
            INSERT OR REPLACE INTO Modules 
            (module_id, module_name, duration, lecture_hours, tutorial_hours, practical_hours) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (mod_code, mod_name, duration, l_hrs, t_hrs, p_hrs))
        
        real_person = row[col_resource]
        if pd.notna(real_person) and real_person in name_map:
            fake_name = name_map[real_person]
            
            cursor.execute("SELECT user_id FROM Users WHERE name = ?", (fake_name,))
            user_record = cursor.fetchone()
            
            if user_record:
                user_id = user_record[0]
                cursor.execute('''
                    INSERT INTO Allocations (user_id, module_id, approval_status) 
                    VALUES (?, ?, 'Approved')
                ''', (user_id, mod_code))

    conn.commit()
    conn.close()
    print(f"Success! {len(name_map)} anonymized lecturers and all modules imported.")

if __name__ == '__main__':
    import_and_anonymize()