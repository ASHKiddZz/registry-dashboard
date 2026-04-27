import streamlit as st
import sqlite3
import pandas as pd
import datetime
import os

# --- BULLETPROOF DATABASE SEEDER ---
DB_FILE = 'registry_database.db'

if not os.path.exists(DB_FILE):
    st.info("Initializing robust database from Excel template...")
    try:
        conn = sqlite3.connect(DB_FILE)
        xls = pd.ExcelFile('mock_university_database.xlsx')
        
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # --- 1. COLUMN-LEVEL SAFETY NET ---
            # If the user completely forgot to include a column, we create it here with a default value.
            if sheet_name == 'Users':
                if 'password' not in df.columns: df['password'] = 'Pass123!'
                if 'hire_year' not in df.columns: df['hire_year'] = 2024
                if 'category_level' not in df.columns: df['category_level'] = 'N/A'
                
            elif sheet_name == 'Modules':
                if 'duration' not in df.columns: df['duration'] = 12
                if 'practical_hours' not in df.columns: df['practical_hours'] = 0
                if 'lecture_hours' not in df.columns: df['lecture_hours'] = 3

            elif sheet_name == 'Modules':
                if 'duration' not in df.columns: df['duration'] = 12
                if 'practical_hours' not in df.columns: df['practical_hours'] = 0
                if 'lecture_hours' not in df.columns: df['lecture_hours'] = 3
            
            # --- ADD THIS NEW BLOCK FOR ALLOCATIONS ---
            elif sheet_name == 'Allocations':
                if 'cohort' not in df.columns: df['cohort'] = 'Group A' # Default cohort
            # ------------------------------------------
            
            elif sheet_name == 'Pending_Promotions':
                if 'status' not in df.columns: df['status'] = 'Pending HoD'
                # --- ADD THIS LINE ---
                if 'rejection_reason' not in df.columns: df['rejection_reason'] = ''
                
            # --- 2. ROW-LEVEL SAFETY NET (Empty Cells) ---
            # If the column exists, but the user left specific cells blank (NaN), we fill those blanks.
            
            # First, fill specific numeric blanks safely
            if 'duration' in df.columns: df['duration'] = df['duration'].fillna(12)
            if 'hire_year' in df.columns: df['hire_year'] = df['hire_year'].fillna(2024)
            if 'cohort' in df.columns: df['cohort'] = df['cohort'].fillna('Group A')
            
            # Then, catch absolutely any other blank text cells and mark them as "Unknown" or empty string
            df = df.fillna('Unknown') 
            
            # Save the clean, repaired dataframe to the SQL database
            df.to_sql(sheet_name, conn, if_exists='replace', index=False)
            
        conn.commit()
        conn.close()
        st.success("Database successfully seeded and cleaned!")
    except Exception as e:
        st.error(f"Critical error seeding database: {e}")

# 1. Setup the Page
st.set_page_config(page_title="Registry Workload System", layout="wide")

# Silent DB Upgrade: Adds hire_year if it doesn't exist yet
patch_conn = sqlite3.connect('registry_database.db')
try:
    patch_conn.execute("ALTER TABLE Users ADD COLUMN hire_year INTEGER DEFAULT 2023")
    patch_conn.commit()
except sqlite3.OperationalError:
    pass # The column already exists, do nothing!
patch_conn.close()

# Silent DB Upgrade 2: Create the Waiting Room for Promotions
patch_conn = sqlite3.connect('registry_database.db')
patch_conn.execute('''
    CREATE TABLE IF NOT EXISTS Pending_Promotions (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        proposed_role TEXT,
        proposed_category TEXT,
        status TEXT DEFAULT 'Pending HoD',
        request_date DATE DEFAULT CURRENT_DATE
    )
''')
patch_conn.commit()
patch_conn.close()

# Silent DB Upgrade 3: Lecturer Remarks Inbox
patch_conn = sqlite3.connect('registry_database.db')
patch_conn.execute('''
    CREATE TABLE IF NOT EXISTS Lecturer_Remarks (
        remark_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        remark_text TEXT,
        status TEXT DEFAULT 'Unread',
        submit_date DATE DEFAULT CURRENT_DATE
    )
''')
patch_conn.commit()
patch_conn.close()

# 2. Database Helper Function
def verify_login(username, password):
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, role FROM Users WHERE name=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

# 3. Initialize Memory (Session State)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = ""
    st.session_state.user_role = ""

# 4. The Login Screen UI
if not st.session_state.logged_in:
    st.title("Login - Registry Workload System")
    
    with st.form("login_form"):
        user_input = st.text_input("Username (e.g., Super Admin or Lecturer 1)")
        password_input = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            user = verify_login(user_input, password_input)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user[0]
                st.session_state.user_name = user[1]
                st.session_state.user_role = user[2]
                st.rerun() 
            else:
                st.error("Invalid Username or Password.")

# 5. The Main Dashboard UI (Logged In)
else:
    st.sidebar.title(f"Welcome, {st.session_state.user_name}")
    st.sidebar.write(f"Role: **{st.session_state.user_role}**")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.clear()
        st.rerun()

    # --- ADMIN TOOLS ---
    st.sidebar.divider()
    if st.sidebar.button("🚨 Reset Database to Default"):
        import os
        # 1. Delete the current messy database
        if os.path.exists('registry_database.db'):
            os.remove('registry_database.db')
        
        # 2. Log the user out so the app restarts completely
        st.session_state.clear()
        
        # 3. Reload the page (triggers the Excel seeder at the top!)
        st.rerun()
        
    # --- PASSWORD UPDATER FEATURE ---
    with st.sidebar.expander("⚙️ Change Password"):
        with st.form("password_form"):
            new_pass = st.text_input("New Password", type="password")
            confirm_pass = st.text_input("Confirm Password", type="password")
            submit_pass = st.form_submit_button("Update")
            
            if submit_pass:
                if new_pass == confirm_pass and len(new_pass) > 0:
                    conn = sqlite3.connect('registry_database.db')
                    cursor = conn.cursor()
                    cursor.execute("UPDATE Users SET password = ? WHERE user_id = ?", 
                                   (new_pass, st.session_state.user_id))
                    conn.commit()
                    conn.close()
                    st.success("Password updated!")
                else:
                    st.error("Passwords must match and not be empty.")

    st.title(f"{st.session_state.user_role} Dashboard")

    
    
    # --- TABBED REGISTRY OFFICER VIEW ---
    def registry_dashboard():
        # --- NOTIFICATION CENTER: Unread Staff Remarks ---
        conn = sqlite3.connect('registry_database.db')
        remarks_df = pd.read_sql_query("""
            SELECT r.remark_id, u.name as "Lecturer Name", r.remark_text as "Remark", r.submit_date as "Date"
            FROM Lecturer_Remarks r
            JOIN Users u ON r.user_id = u.user_id
            WHERE r.status = 'Unread'
        """, conn)

        if not remarks_df.empty:
            # st.expander creates a drop-down box that is bright and noticeable
            with st.expander("🔔 FLAG: Unread Staff Remarks (Action Required)", expanded=True):
                st.dataframe(remarks_df, hide_index=True, use_container_width=True)
            
                with st.form("clear_remark_form"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        ack_id = st.selectbox("Select Remark ID to clear", remarks_df['remark_id'])
                    with col2:
                        st.write("") # Spacing
                        st.write("")
                        if st.form_submit_button("Acknowledge & Clear"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE Lecturer_Remarks SET status = 'Read' WHERE remark_id = ?", (ack_id,))
                            conn.commit()
                            st.success("Remark cleared from dashboard!")
                            st.rerun()
        conn.close()
    
        st.divider()
        
        tab1, tab2, tab3, tab4 = st.tabs(["Manage Users", "Manage Modules", "Allocations Overview", "Promotions & Rotations"])
        
        with tab1:
            st.subheader("Current System Users")
            conn = sqlite3.connect('registry_database.db')
            users_df = pd.read_sql_query("SELECT user_id, name, role, category_level FROM Users", conn)
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- NEW: Edit or Delete Existing User ---
            st.subheader("Edit or Delete Staff")
            
            # Create a combined string for the dropdown (e.g., "1 - Super Admin")
            user_list = users_df['user_id'].astype(str) + " - " + users_df['name']
            selected_user_str = st.selectbox("Select User to Modify", user_list)
            
            if selected_user_str:
                # Extract just the ID number from the string
                selected_id = int(selected_user_str.split(" - ")[0])
                
                # Grab that specific user's current data to fill the default values
                current_data = users_df[users_df['user_id'] == selected_id].iloc[0]
                
                col1, col2 = st.columns(2)
                with col1:
                    # Remember: This "Name" is what they use to log in (their username)
                    edit_name = st.text_input("Update Name (Username)", value=current_data['name'])
                    
                    roles = ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor", "HoD", "HoS", "Registry Officer"]
                    current_role = current_data['role']
                    role_index = roles.index(current_role) if current_role in roles else 0
                    edit_role = st.selectbox("Update Role", roles, index=role_index)
                    
                with col2:
                    levels = ["Category 1 (HoS)", "Category 2 (HoD)", "Category 3 (TBD)", "Category 4 (PhD Staff)", "Category 5 (Other Academic)", "N/A"]
                    current_level = current_data['category_level']
                    level_index = levels.index(current_level) if current_level in levels else 0
                    edit_level = st.selectbox("Update Category", levels, index=level_index)
                    
                    # --- THE NEW PASSWORD RESET FIELD ---
                    edit_password = st.text_input("Reset Password (leave blank to keep current)", type="password")
                    
                st.write("Actions:")
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("Update User", use_container_width=True):
                        cursor = conn.cursor()
                        # If the admin typed a new password, update everything
                        if edit_password: 
                            cursor.execute("UPDATE Users SET name=?, role=?, category_level=?, password=? WHERE user_id=?", 
                                           (edit_name, edit_role, edit_level, edit_password, selected_id))
                        # If left blank, update everything EXCEPT the password
                        else: 
                            cursor.execute("UPDATE Users SET name=?, role=?, category_level=? WHERE user_id=?", 
                                           (edit_name, edit_role, edit_level, selected_id))
                        conn.commit()
                        st.success(f"User updated successfully!")
                        st.rerun()
                        
                with btn_col2:
                    if st.button("Delete User", type="primary", use_container_width=True):
                        if selected_id == 1:
                            st.error("Security Alert: You cannot delete the master Super Admin account!")
                        else:
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM Users WHERE user_id=?", (selected_id,))
                            cursor.execute("DELETE FROM Allocations WHERE user_id=?", (selected_id,))
                            conn.commit()
                            st.warning(f"User deleted from system!")
                            st.rerun()

            st.divider()
            
            # --- RESTORED: Add User Form ---
            st.subheader("Register New Staff Member")
            with st.form("add_user_form", clear_on_submit=True):
                new_name = st.text_input("Full Name")
                new_role = st.selectbox("Role", ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor", "HoD", "HoS", "Registry Officer"])
                new_level = st.selectbox("Category Limit", ["Category 1 (HoS)", "Category 2 (HoD)", "Category 3 (TBD)", "Category 4 (PhD Staff)", "Category 5 (Other Academic)", "N/A"])
    
                # --- NEW: Hire Year Input ---
                current_yr = datetime.datetime.now().year
                new_hire_year = st.number_input("Year Hired", min_value=1990, max_value=current_yr, value=current_yr)
    
                new_pass = st.text_input("Temporary Password", type="password")

                submit_user = st.form_submit_button("Create Account")

                if submit_user:
                    if new_name and new_pass:
                        cursor = conn.cursor()
                        # --- NEW: Updated INSERT command to include hire_year ---
                        cursor.execute("INSERT INTO Users (name, role, category_level, password, hire_year) VALUES (?, ?, ?, ?, ?)", 
                                       (new_name, new_role, new_level, new_pass, new_hire_year))
                        conn.commit()
                        st.success(f"Account created for {new_name}!")
                        st.rerun()
                    else:
                        st.error("Please fill out the Name and Password fields.")
            conn.close()

        st.divider() # Creates a nice visual line break
        st.subheader("📥 Bulk Import Staff (Annex Upload)")

        # 1. Create the drag-and-drop zone
        uploaded_file = st.file_uploader("Upload staff list (CSV or Excel)", type=['csv', 'xlsx'])

        if uploaded_file is not None:
            # 2. Read the file into Pandas
            try:
                if uploaded_file.name.endswith('.csv'):
                    import_df = pd.read_csv(uploaded_file)
                else:
                    import_df = pd.read_excel(uploaded_file)
            
                st.write("Preview of uploaded document:")
                st.dataframe(import_df.head(3)) # Show the first 3 rows

                # 3. The Import Button
                if st.button("Process & Import Users"):
                    cursor = conn.cursor()
                    added_count = 0
                    skipped_count = 0

                    for index, row in import_df.iterrows():
                        # NOTE: You must change 'Name' and 'Role' to match the exact column headers in your annex file!
                        staff_name = str(row.get('Name', '')).strip()
                        staff_role = str(row.get('Role', '')).strip()
                        category = str(row.get('Category_Level', 'N/A')).strip()

                        # Make sure the row isn't blank
                        if staff_name and staff_name != 'nan':

                            # Check if this person is already in the database
                            cursor.execute("SELECT * FROM Users WHERE name=?", (staff_name,))
                            if not cursor.fetchone():
                                # Create the account with a default password
                                cursor.execute("INSERT INTO Users (name, role, category_level, password) VALUES (?, ?, ?, ?)",
                                               (staff_name, staff_role, category, 'welcome123'))
                                added_count += 1
                            else:
                                skipped_count += 1 # Person already exists, skip them!

                    conn.commit()

                    if added_count > 0:
                        st.success(f"✅ Successfully imported {added_count} new users! (Skipped {skipped_count} duplicates)")
                    else:
                        st.warning(f"⚠️ No new users added. All {skipped_count} people were already in the system.")

            except Exception as e:
                st.error(f"Could not read the file. Error: {e}")

        with tab2:
            st.subheader("University Modules Database")
            conn = sqlite3.connect('registry_database.db')
            modules_df = pd.read_sql_query("SELECT * FROM Modules", conn)
            
            # --- NEW: Clean up the column names for the display table ---
            display_df = modules_df.rename(columns={
                'module_id': 'Module Code',
                'module_name': 'Module Name',
                'duration': 'Duration (Weeks)',
                'lecture_hours': 'Lecture Hrs',
                'tutorial_hours': 'Tutorial Hrs',
                'practical_hours': 'Practical Hrs'
            })
            
            # Display the cleaned-up dataframe instead of the raw database one
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- NEW: Edit or Delete Existing Module ---
            st.subheader("Edit or Delete Module")
            
            if not modules_df.empty:
                # Create a combined string for the dropdown (e.g., "PROG1101C - Programming Concepts")
                module_list = modules_df['module_id'].astype(str) + " - " + modules_df['module_name']
                selected_mod_str = st.selectbox("Select Module to Modify", module_list)
                
                if selected_mod_str:
                    # Extract just the module_id from the string
                    selected_mod_id = selected_mod_str.split(" - ")[0]
                    
                    # Grab current data
                    current_mod_data = modules_df[modules_df['module_id'] == selected_mod_id].iloc[0]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        # We lock the Module Code as read-only info so they don't break database links
                        st.info(f"Editing Module Code: **{selected_mod_id}**")
                        edit_m_name = st.text_input("Update Module Name", value=current_mod_data['module_name'])
                        # Check if the column exists to prevent crashes. Default to 12 if missing.
                        default_dur = int(current_mod_data['duration']) if 'duration' in current_mod_data else 12
                        # --- BULLETPROOF DURATION CHECK ---
                    try:
                        default_dur = int(current_mod_data['duration'])
                    except KeyError:
                        default_dur = 12 # Fallback if the database is stubborn

                        edit_duration = st.number_input("Update Duration (Weeks)", min_value=1, value=default_dur)
# ----------------------------------
                        
                    with col2:
                        edit_l_hrs = st.number_input("Update Lecture Hours (L)", min_value=0, value=int(current_mod_data['lecture_hours']))
                        # --- BULLETPROOF TUTORIAL HOURS CHECK ---
                    try:
                        default_t_hrs = int(current_mod_data['tutorial_hours'])
                    except KeyError:
                        default_t_hrs = 0 # Fallback if the database is missing this column

                        edit_t_hrs = st.number_input("Update Tutorial Hours (T)", min_value=0, value=default_t_hrs)
# ----------------------------------------
                        # --- BULLETPROOF PRACTICAL HOURS CHECK ---
                        try:
                            # Try to grab the number
                            default_p_hrs = int(current_mod_data['practical_hours'])
                        except (KeyError, ValueError):
                            # If the column is missing (KeyError) OR the cell is blank/text (ValueError), default to 0
                            default_p_hrs = 0 

                        edit_p_hrs = st.number_input("Update Practical Hours (P)", min_value=0, value=default_p_hrs)
# -----------------------------------------
                        
                    st.write("Actions:")
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Update Module", use_container_width=True):
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE Modules 
                                SET module_name=?, duration=?, lecture_hours=?, tutorial_hours=?, practical_hours=? 
                                WHERE module_id=?
                            ''', (edit_m_name, edit_duration, edit_l_hrs, edit_t_hrs, edit_p_hrs, selected_mod_id))
                            conn.commit()
                            st.success("Module updated successfully!")
                            st.rerun()
                            
                    with btn_col2:
                        if st.button("Delete Module", type="primary", use_container_width=True):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM Modules WHERE module_id=?", (selected_mod_id,))
                            # Delete any allocations attached to this module to prevent ghost data
                            cursor.execute("DELETE FROM Allocations WHERE module_id=?", (selected_mod_id,))
                            conn.commit()
                            st.warning("Module deleted from system!")
                            st.rerun()

            st.divider()
            
            # --- RESTORED: Bulk Import Excel ---
            st.subheader("Bulk Import Modules")
            st.info("Upload the final Allocation Excel document here when it arrives.")
            uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
            if uploaded_file is not None:
                df = pd.read_excel(uploaded_file)
                st.write("File Preview:")
                st.dataframe(df.head())
                
                if st.button("Import Data to Database"):
                    cursor = conn.cursor()
                    success_count = 0
                    for index, row in df.iterrows():
                        cursor.execute('''
                            INSERT OR REPLACE INTO Modules 
                            (module_id, module_name, duration, lecture_hours, tutorial_hours, practical_hours) 
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            str(row['Module Code']), str(row['Module Name']), int(row['Duration (Weeks)']), 
                            int(row['Lecture Hours (L)']), int(row['Tutorial Hours (T)']), int(row['Practical Hours (P)'])
                        ))
                        success_count += 1
                    conn.commit()
                    st.success(f"Successfully imported {success_count} modules from Excel!")
                    st.rerun()
            
            st.divider()
            
            # --- RESTORED: Manually Add Module Form ---
            st.subheader("Manually Add a Module")
            with st.form("add_module_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    m_id = st.text_input("Module Code (e.g., SE101)")
                    m_name = st.text_input("Module Name (e.g., Software Engineering)")
                    m_duration = st.number_input("Duration (Weeks)", min_value=1, value=15)
                with col2:
                    l_hrs = st.number_input("Lecture Hours (L)", min_value=0, value=0)
                    t_hrs = st.number_input("Tutorial Hours (T)", min_value=0, value=0)
                    p_hrs = st.number_input("Practical Hours (P)", min_value=0, value=0)
                    
                submit_mod = st.form_submit_button("Save Module to Database")
                
                if submit_mod:
                    if m_id and m_name:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO Modules (module_id, module_name, duration, lecture_hours, tutorial_hours, practical_hours) VALUES (?, ?, ?, ?, ?, ?)", 
                                       (m_id, m_name, m_duration, l_hrs, t_hrs, p_hrs))
                        conn.commit()
                        st.success(f"Module {m_id} successfully added!")
                        st.rerun()
                    else:
                        st.error("Module Code and Name are required.")
            conn.close()

        with tab3:
            st.subheader("Workload & Allocations Overview")
            conn = sqlite3.connect('registry_database.db')
            
            # --- PART 1: THE SMART WORKLOAD MATH ---
            st.markdown("### Lecturer Workload Analysis")
            st.info("💡 Lecturers exceeding their category limit are highlighted automatically.")
            
            # The workload math counts EACH cohort as a separate workload assignment
            workload_query = """
                SELECT u.name as "Lecturer", u.category_level as "Category", COUNT(a.module_id) as "Assigned Modules"
                FROM Users u
                LEFT JOIN Allocations a ON u.user_id = a.user_id
                WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')
                GROUP BY u.user_id, u.name, u.category_level
            """
            workload_df = pd.read_sql_query(workload_query, conn)
            
            def get_category_limit(category):
                if pd.isna(category): return 99 
                if "Cat 1" in category: return 2
                if "Cat 4" in category: return 5
                if "Cat 5" in category: return 6
                return 99 
                
            workload_df['Limit'] = workload_df['Category'].apply(get_category_limit)
            workload_df['Excess'] = workload_df['Assigned Modules'] - workload_df['Limit']
            workload_df['Excess'] = workload_df['Excess'].apply(lambda x: x if x > 0 else 0)
            workload_df['Status'] = workload_df['Excess'].apply(lambda x: "🚨 OVERLOAD" if x > 0 else "✅ OK")
            
            def highlight_overload(row):
                if row['Excess'] > 0:
                    return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
                return [''] * len(row)

            styled_df = workload_df.style.apply(highlight_overload, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- PART 2: THE DETAILED MASTER LIST ---
            st.markdown("### Detailed Master List")
            
            # NEW: We now select the 'cohort' column to display in the table
            all_data = pd.read_sql_query("""
                SELECT u.name as "Lecturer", a.module_id as "Module Code", m.module_name as "Module Title", a.cohort as "Cohort/Group"
                FROM Allocations a
                JOIN Users u ON a.user_id = u.user_id
                JOIN Modules m ON a.module_id = m.module_id
            """, conn)
            
            lecturer_options = ["All Lecturers"] + sorted(all_data['Lecturer'].unique().tolist())
            selected_filter = st.selectbox("🔍 Search / Filter by Lecturer", lecturer_options)
            
            if selected_filter != "All Lecturers":
                display_data = all_data[all_data['Lecturer'] == selected_filter]
            else:
                display_data = all_data
                
            st.caption(f"Showing **{len(display_data)}** assigned module(s).")
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
            st.divider()

            # --- PART 3: MANAGE ALLOCATIONS ---
            st.markdown("### Manual Assignment Control")
            col1, col2 = st.columns(2)
            
            # --- Left Side: Assign ---
            with col1:
                st.write("**Assign a Module to Staff**")
                with st.form("assign_form", clear_on_submit=True):
                    staff_df = pd.read_sql_query("SELECT user_id, name FROM Users WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')", conn)
                    
                    # NEW: Check if the staff list is empty first
                    if staff_df.empty:
                        st.warning("⚠️ No teaching staff found. Please register a Lecturer in the Manage Users tab first.")
                        st.form_submit_button("Assign Module", disabled=True)
                    else:
                        staff_list = staff_df['user_id'].astype(str) + " - " + staff_df['name']
                        selected_staff = st.selectbox("Select Staff Member", staff_list)
                        
                        mod_df = pd.read_sql_query("SELECT module_id, module_name FROM Modules", conn)
                        
                        # NEW: Check if the modules list is empty first
                        if mod_df.empty:
                            st.warning("⚠️ No modules found. Please add modules first.")
                            st.form_submit_button("Assign Module", disabled=True)
                        else:
                            mod_list = mod_df['module_id'].astype(str) + " - " + mod_df['module_name']
                            selected_mod = st.selectbox("Select Module", mod_list)
                            
                            assign_cohort = st.text_input("Cohort / Group", value="Group A", help="e.g., Group A, Group B, PT1, etc.")
                            
                            submit_assign = st.form_submit_button("Assign Module")
                            
                            if submit_assign:
                                s_id = int(selected_staff.split(" - ")[0])
                                m_id = selected_mod.split(" - ")[0]
                                
                                cursor = conn.cursor()
                                cursor.execute("SELECT * FROM Allocations WHERE user_id=? AND module_id=? AND cohort=?", (s_id, m_id, assign_cohort))
                                if cursor.fetchone():
                                    st.error(f"This person is already teaching {m_id} for {assign_cohort}!")
                                else:
                                    cursor.execute("INSERT INTO Allocations (user_id, module_id, cohort) VALUES (?, ?, ?)", (s_id, m_id, assign_cohort))
                                    conn.commit()
                                    st.success(f"Assigned {assign_cohort} successfully!")
                                    st.rerun()

            # --- Right Side: Remove ---
            with col2:
                st.write("**Remove an Allocation**")
                with st.form("remove_form"):
                    # NEW: Include the cohort in the removal query
                    alloc_df = pd.read_sql_query("""
                        SELECT a.user_id, u.name, a.module_id, m.module_name, a.cohort
                        FROM Allocations a
                        JOIN Users u ON a.user_id = u.user_id
                        JOIN Modules m ON a.module_id = m.module_id
                    """, conn)
                    
                    if not alloc_df.empty:
                        # NEW: The string now shows the cohort so the admin knows exactly which one to delete
                        alloc_list = alloc_df['user_id'].astype(str) + "|" + alloc_df['module_id'] + "|" + alloc_df['cohort'] + " : " + alloc_df['name'] + " - " + alloc_df['module_name'] + " (" + alloc_df['cohort'] + ")"
                        selected_alloc = st.selectbox("Select Assignment to Remove", alloc_list)
                        
                        submit_remove = st.form_submit_button("Remove Allocation", type="primary")
                        
                        if submit_remove:
                            keys = selected_alloc.split(" : ")[0].split("|")
                            r_uid = int(keys[0])
                            r_mid = keys[1]
                            r_cohort = keys[2] # Extract the cohort text
                            
                            cursor = conn.cursor()
                            # Delete the exact cohort match
                            cursor.execute("DELETE FROM Allocations WHERE user_id=? AND module_id=? AND cohort=?", (r_uid, r_mid, r_cohort))
                            conn.commit()
                            st.success("Allocation removed successfully!")
                            st.rerun()
                    else:
                        st.info("There are no allocations to remove.")
                        st.form_submit_button("Remove Allocation", disabled=True)

            conn.close()

        # ==========================================
        #         TAB 4: PROMOTION MANAGEMENT
        # ==========================================
        with tab4:
            st.header("📋 Promotion Management")

            conn = sqlite3.connect('registry_database.db')

            # --- PART 1: THE ELIGIBILITY RADAR (TRACKING) ---
            st.subheader("📡 Eligibility Radar")
            st.write("Monitor staff who currently meet the workload and tenure requirements for promotion.")
            
            current_yr = datetime.datetime.now().year
            
            try:
                radar_df = pd.read_sql_query(f"""
                    SELECT u.name as "Staff Member", u.role as "Current Role", 
                           ({current_yr} - u.hire_year) as "Years Served", 
                           COUNT(a.module_id) as "Active Modules"
                    FROM Users u
                    LEFT JOIN Allocations a ON u.user_id = a.user_id
                    WHERE u.category_level IN ('Category 5 (Other Academic)', 'Category 4 (PhD Staff)')
                    GROUP BY u.user_id
                    HAVING "Years Served" >= 3 AND "Active Modules" >= 3
                """, conn)
                
                if radar_df.empty:
                    st.info("No staff currently meet the baseline eligibility criteria.")
                else:
                    st.dataframe(radar_df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Error loading radar: {e}")

            st.divider()

            # --- PART 2: THE VERIFICATION QUEUE (ACTIONABLE) ---
            st.subheader("📥 Application Verification Queue")
            st.write("Review promotion applications submitted by teaching staff before forwarding them to Department Heads.")

            try:
                # Only pull tickets waiting for Registry verification
                queue_df = pd.read_sql_query("""
                    SELECT p.ticket_id, u.name as "Applicant", u.role as "Current Role", 
                           p.proposed_role as "Requested Role", p.proposed_category as "Requested Category"
                    FROM Pending_Promotions p
                    JOIN Users u ON p.user_id = u.user_id
                    WHERE p.status = 'Pending Registry'
                """, conn)

                if queue_df.empty:
                    st.success("✅ No new promotion applications require verification at this time.")
                else:
                    st.dataframe(queue_df, use_container_width=True, hide_index=True)

                    st.write("### Process Application")

                    with st.form("registry_verify_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            selected_ticket = st.selectbox("Select Ticket ID", queue_df['ticket_id'])
                        with col2:
                            action = st.radio("Registry Decision", ["Verify & Forward to HoD", "Reject (Ineligible)"], horizontal=True)

                        rejection_reason = st.text_area("Rejection Reason (Required if Rejecting)")

                        if st.form_submit_button("Submit Verification", use_container_width=True):
                            if "Reject" in action and not rejection_reason.strip():
                                st.error("You must provide a reason for rejecting the application.")
                            else:
                                cursor = conn.cursor()
                                new_status = 'Pending HoD' if 'Verify' in action else 'Rejected'

                                cursor.execute("UPDATE Pending_Promotions SET status = ?, rejection_reason = ? WHERE ticket_id = ?", (new_status, rejection_reason, selected_ticket))
                                conn.commit()
                                st.success(f"Ticket #{selected_ticket} processed. New Status: {new_status}")
                                st.rerun()
            except Exception as e:
                st.error(f"Error loading verification queue: {e}")
                
            conn.close()

        

    # --- LECTURER VIEW ---
    def lecturer_dashboard():
        st.title(f"👋 Welcome, {st.session_state.user_name}")
        
        conn = sqlite3.connect('registry_database.db')
        
        # 1. Fetch Profile & Workload
        user_info = pd.read_sql_query("SELECT role, category_level, hire_year FROM Users WHERE user_id = ?", 
                                      conn, params=(st.session_state.user_id,)).iloc[0]
        
        my_modules = pd.read_sql_query("""
            SELECT m.module_id as "Code", m.module_name as "Module Title", 
                   m.lecture_hours as "L", m.practical_hours as "P"
            FROM Allocations a
            JOIN Modules m ON a.module_id = m.module_id
            WHERE a.user_id = ?
        """, conn, params=(st.session_state.user_id,))
        
        current_yr = datetime.datetime.now().year # Made this dynamic using your global datetime!
        years_served = current_yr - user_info['hire_year']
        workload_count = len(my_modules)

        # --- TOP ROW: Quick Stats ---
        col1, col2, col3 = st.columns(3)
        col1.metric("Current Role", user_info['role'])
        col2.metric("Teaching Load", f"{workload_count} Modules")
        col3.metric("Service Time", f"{years_served} Years")

        st.divider()

        # --- SECTION: UPGRADED VISUAL PROMOTION TRACKER ---
        st.subheader("🚀 Promotion Tracker")
        st.write("Monitor the real-time status of your career advancement requests.")
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticket_id, proposed_role, proposed_category, status, rejection_reason 
            FROM Pending_Promotions 
            WHERE user_id = ?
            ORDER BY ticket_id DESC
        """, (st.session_state.user_id,))
        
        my_requests = cursor.fetchall()
        
        if not my_requests:
            # Check eligibility
            if workload_count >= 3 and years_served >= 3:
                st.success("✅ You meet the baseline criteria to apply for a promotion!")
                
                # --- NEW: LECTURER SUBMISSION FORM ---
                with st.form("lecturer_promo_form"):
                    st.write("Submit your application to the Registry Office for verification:")
                    req_role = st.selectbox("Requested Title", ["Senior Lecturer", "Associate Professor", "Professor"])
                    req_category = st.selectbox("Requested Category", ["Category 1 (Management)", "Category 2 (Professional)", "Category 3 (Technical)", "Category 4 (PhD Staff)", "Category 5 (Other Academic)"])
                    
                    if st.form_submit_button("Submit Application"):
                        cursor.execute("SELECT MAX(ticket_id) FROM Pending_Promotions")
                        max_id_result = cursor.fetchone()[0]
                        new_ticket_id = 1 if max_id_result is None else int(max_id_result) + 1
                        
                        # Note the new status: 'Pending Registry'
                        cursor.execute("""
                            INSERT INTO Pending_Promotions (ticket_id, user_id, proposed_role, proposed_category, status, rejection_reason)
                            VALUES (?, ?, ?, ?, 'Pending Registry', '')
                        """, (new_ticket_id, st.session_state.user_id, req_role, req_category))
                        
                        conn.commit()
                        st.success("Application successfully submitted to the Registry Office!")
                        st.rerun()
            else:
                st.info("Keep up the great work! You are currently working toward promotion eligibility.")
        else:
            # Loop through every request and build a visual "Tracking Card"
            for req in my_requests:
                t_id, p_role, p_cat, status, rej_reason = req
                
                with st.container(border=True):
                    st.markdown(f"**Requested Promotion:** {p_role} *( {p_cat} )*")
                    
                    # --- UPDATED DUAL-STAGE PROGRESS BAR ---
                    if status == 'Pending Registry':
                        st.info("📋 **Current Status:** Awaiting Registry Verification")
                        st.progress(25) # Step 1
                    elif status == 'Pending HoD':
                        st.warning("⏳ **Current Status:** Awaiting Department Head (HoD) Review")
                        st.progress(50) # Step 2
                    elif status == 'Pending HoS':
                        st.info("🔍 **Current Status:** Awaiting Final Head of School (HoS) Approval")
                        st.progress(75) # Step 3
                    elif status == 'Approved':
                        st.success("🎉 **Current Status:** Approved! Your official title has been updated.")
                        st.progress(100) # Finish Line
                    elif status == 'Rejected':
                        st.error("❌ **Current Status:** Rejected.")
                        st.write(f"**Official Feedback:** {rej_reason}")

        st.divider()

        # --- SECTION: Remarks for Registry ---
        st.subheader("💬 Registry Communications")
        with st.form("registry_remarks_form"):
            st.write("Submit a remark or flag an issue regarding your workload/modules directly to the Registry.")
            remark = st.text_area("Enter your remark here:")
            
            if st.form_submit_button("Send to Registry"):
                if remark.strip(): 
                    today_date = datetime.date.today().strftime("%Y-%m-%d") # Removed the local import!
                    
                    cursor = conn.cursor()
                    
                    cursor.execute("SELECT MAX(remark_id) FROM Lecturer_Remarks")
                    max_id_result = cursor.fetchone()[0]
                    
                    new_remark_id = 1 if max_id_result is None else int(max_id_result) + 1
                    
                    cursor.execute("""
                        INSERT INTO Lecturer_Remarks (remark_id, user_id, remark_text, status, submit_date) 
                        VALUES (?, ?, ?, 'Unread', ?)
                    """, (new_remark_id, st.session_state.user_id, remark, today_date))
                    
                    conn.commit()
                    st.success("Your remark has been successfully flagged for the Registry Office!")
                else:
                    st.error("Please type a remark before submitting.")
                    
        st.divider()

        # --- SECTION: Module List ---
        st.subheader("📚 Assigned Modules")
        if not my_modules.empty:
            st.dataframe(my_modules, use_container_width=True, hide_index=True)
        else:
            st.info("No modules assigned for this semester yet.")

        conn.close()
        
    # --- TABBED HOD VIEW ---
    def hod_dashboard():
        st.title("🎓 Head of Department Dashboard")
        st.write("Oversee departmental module allocations and review staff promotion requests.")
        
        tab1, tab2 = st.tabs(["Department Allocations", "Staff Promotions"])
        
        # --- TAB 1: ALLOCATIONS OVERVIEW ---
        with tab1:
            st.subheader("Current Module Allocations")
            conn = sqlite3.connect('registry_database.db')
            try:
                alloc_df = pd.read_sql_query("""
                    SELECT u.name as "Lecturer", a.module_id as "Module Code", m.module_name as "Module Title"
                    FROM Allocations a
                    JOIN Users u ON a.user_id = u.user_id
                    JOIN Modules m ON a.module_id = m.module_id
                """, conn)
                
                # --- THE NEW DUAL-FILTER SYSTEM ---
                col1, col2 = st.columns(2)
                
                with col1:
                    lecturer_list = ["All Lecturers"] + sorted(alloc_df["Lecturer"].unique().tolist())
                    selected_lecturer = st.selectbox("👤 Filter by Lecturer", lecturer_list)
                    
                with col2:
                    module_list = ["All Modules"] + sorted(alloc_df["Module Code"].unique().tolist())
                    selected_module = st.selectbox("📚 Filter by Module Code", module_list)
                
                # Start with the full dataframe
                display_df = alloc_df
                
                # Apply Lecturer filter if used
                if selected_lecturer != "All Lecturers":
                    display_df = display_df[display_df["Lecturer"] == selected_lecturer]
                    
                # Apply Module filter if used
                if selected_module != "All Modules":
                    display_df = display_df[display_df["Module Code"] == selected_module]
                    
                # --- DYNAMIC METRICS ---
                # We add two metric boxes to show real-time stats based on the filters
                met_col1, met_col2 = st.columns(2)
                with met_col1:
                    st.metric(label="Total Assigned Modules", value=len(display_df))
                with met_col2:
                    st.metric(label="Unique Lecturers", value=display_df["Lecturer"].nunique())
                
                # Display the final filtered table
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                # -----------------------------------
                
            except Exception as e:
                st.error(f"Error loading allocations: {e}")
            conn.close()

        # --- TAB 2: PROMOTION APPROVALS ---
        with tab2:
            st.subheader("Promotion Requests (Action Required)")
            conn = sqlite3.connect('registry_database.db')
            try:
                # Only pull tickets that are specifically waiting for the HoD
                promo_df = pd.read_sql_query("""
                    SELECT p.ticket_id, u.name as "Applicant", u.role as "Current Role", 
                        p.proposed_role as "Requested Role", p.proposed_category as "Requested Category", p.status
                    FROM Pending_Promotions p
                    JOIN Users u ON p.user_id = u.user_id
                    WHERE p.status = 'Pending HoD'
                """, conn)
                
                if promo_df.empty:
                    st.info("✅ No pending promotions require your approval at this time.")
                else:
                    # Display the pending requests
                    st.dataframe(promo_df, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    st.write("### Process a Request")
                    
                    with st.form("hod_promo_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            selected_ticket = st.selectbox("Select Ticket ID", promo_df['ticket_id'])
                        with col2:
                            action = st.radio("Decision", ["Approve (Forward to HoS)", "Reject"], horizontal=True)
                            
                        # --- NEW: Mandatory Feedback Box ---
                        rejection_reason = st.text_area("Rejection Reason (Required if Rejecting)")
                        
                        if st.form_submit_button("Submit Decision", use_container_width=True):
                            # Catch them if they try to reject without giving a reason
                            if "Reject" in action and not rejection_reason.strip():
                                st.error("You must provide a rejection reason for the applicant.")
                            else:
                                cursor = conn.cursor()
                                new_status = 'Pending HoS' if 'Approve' in action else 'Rejected'
                                
                                # Save both the status and the reason to the database
                                cursor.execute("UPDATE Pending_Promotions SET status = ?, rejection_reason = ? WHERE ticket_id = ?", (new_status, rejection_reason, selected_ticket))
                                conn.commit()
                                st.success(f"Ticket #{selected_ticket} has been marked as: {new_status}")
                                st.rerun()
            except Exception as e:
                st.error(f"Error loading promotions: {e}")
            conn.close()

    # --- TABBED HOS VIEW ---
    def hos_dashboard():
        st.title("🏛️ Head of School Dashboard")
        st.write("Finalize staff promotions and oversee school-wide metrics.")
        
        tab1, tab2 = st.tabs(["Final Promotion Approvals", "School Overview"])
        
        # --- TAB 1: FINAL PROMOTION APPROVALS ---
        with tab1:
            st.subheader("Pending Final Approvals")
            conn = sqlite3.connect('registry_database.db')
            try:
                # Only pull tickets that have been forwarded by the HoD
                promo_df = pd.read_sql_query("""
                    SELECT p.ticket_id, u.name as "Applicant", u.role as "Current Role", 
                        p.proposed_role as "Requested Role", p.proposed_category as "Requested Category"
                FROM Pending_Promotions p
                JOIN Users u ON p.user_id = u.user_id
                WHERE p.status = 'Pending HoS'
                """, conn)
                
                if promo_df.empty:
                    st.info("✅ No promotions require final approval at this time.")
                else:
                    st.dataframe(promo_df, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    st.write("### Finalize Request")
                    
                    with st.form("hos_promo_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            selected_ticket = st.selectbox("Select Ticket ID", promo_df['ticket_id'])
                        with col2:
                            action = st.radio("Final Decision", ["Approve & Apply Promotion", "Reject"], horizontal=True)
                            
                        if st.form_submit_button("Submit Final Decision", use_container_width=True):
                            cursor = conn.cursor()
                            
                            if "Approve" in action:
                                # 1. Grab the exact details of the requested promotion
                                cursor.execute("SELECT user_id, proposed_role, proposed_category FROM Pending_Promotions WHERE ticket_id = ?", (selected_ticket,))
                                ticket_data = cursor.fetchone()
                                target_user_id = ticket_data[0]
                                new_role = ticket_data[1]
                                new_category = ticket_data[2]
                                
                                # 2. THE MAGIC: Actually update the user's official profile in the database!
                                cursor.execute("UPDATE Users SET role = ?, category_level = ? WHERE user_id = ?", (new_role, new_category, target_user_id))
                                
                                # 3. Mark the ticket as officially completed
                                cursor.execute("UPDATE Pending_Promotions SET status = 'Approved' WHERE ticket_id = ?", (selected_ticket,))
                                st.success(f"Promotion Approved! The applicant's official role has been updated to {new_role}.")
                            else:
                                # Mark the ticket as rejected
                                cursor.execute("UPDATE Pending_Promotions SET status = 'Rejected' WHERE ticket_id = ?", (selected_ticket,))
                                st.warning(f"Ticket #{selected_ticket} has been Rejected.")
                                
                            conn.commit()
                            st.rerun()
            except Exception as e:
                st.error(f"Error loading promotions: {e}")
            conn.close()

        # --- TAB 2: SCHOOL OVERVIEW ---
        with tab2:
            st.subheader("School-Wide Staff Metrics")
            conn = sqlite3.connect('registry_database.db')
            try:
                # A quick group-by query to show the HoS how many staff they have in each role
                users_df = pd.read_sql_query("SELECT role as 'Staff Role', COUNT(user_id) as 'Total Count' FROM Users GROUP BY role", conn)
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.dataframe(users_df, use_container_width=True, hide_index=True)
                with col2:
                    # Add a quick metric for total modules across the whole school
                    total_mods = pd.read_sql_query("SELECT COUNT(*) FROM Modules", conn).iloc[0,0]
                    st.metric("Total Modules Run by School", total_mods)
                    
                    # Metric for total staff
                    total_staff = users_df['Total Count'].sum()
                    st.metric("Total School Staff", total_staff)
            except Exception as e:
                st.error(f"Error loading overview: {e}")
            conn.close()

# ==========================================
#      THE TRAFFIC COP (ROLE-BASED ROUTING)
# ==========================================

# 1. Diagnostic Line (Helps us see if there's a typo in the role name)
if 'user_role' in st.session_state:
    st.sidebar.write(f"Logged in as: **{st.session_state.user_role}**")

    # 2. The Routing Logic
    if st.session_state.user_role == "Registry Officer":
        registry_dashboard()
        
    elif st.session_state.user_role == "HoD":
        hod_dashboard()
        
    elif st.session_state.user_role == "HoS":
        hos_dashboard()
        
    elif st.session_state.user_role in ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor"]:
        lecturer_dashboard()
        
    else:
        st.error("Access Denied: Your role is not recognized by the system.")
else:
    st.warning("Please log in to access the dashboard.")

