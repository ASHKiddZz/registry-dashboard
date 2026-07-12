#import of libraries to make app more efficient
import streamlit as st
import sqlite3
from sqlalchemy import create_engine
import pandas as pd
import datetime
import os
import io
from fpdf import FPDF

st.set_page_config(page_title="Registry Workload System", layout="wide")

# --- THE MAGICAL CLOUD BRIDGE ---
CLOUD_DB_URL = "postgresql://postgres.ttzgfkbtpxpkjslektkv:UTM89786756@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

@st.cache_resource
def init_engine():
    return create_engine(CLOUD_DB_URL)

cloud_engine = init_engine()

class CloudCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        
    def execute(self, query, params=None):
        # 1. Translate SQLite '?' to Postgres '%s'
        query = query.replace('?', '%s') 
        
        # 2. THE FIX: Wrap table names in double quotes to force Case Sensitivity
        # We replace " FROM Users " with " FROM \"Users\" "
        tables = ["Users", "Modules", "Allocations", "Lecturer_Remarks", "Pending_Promotions"]
        for table in tables:
            # We look for the table name and wrap it in \"
            query = query.replace(f" {table} ", f' "{table}" ')
            query = query.replace(f"FROM {table}", f'FROM "{table}"')
            query = query.replace(f"JOIN {table}", f'JOIN "{table}"')
        
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self
        
    def fetchone(self):
        return self.cursor.fetchone()
        
    def fetchall(self):
        return self.cursor.fetchall()
        
    @property
    def description(self):
        return self.cursor.description
        
    @property
    def rowcount(self):
        return self.cursor.rowcount
        
    def close(self):
        self.cursor.close()

class CloudConnection:
    def __init__(self):
        self.conn = cloud_engine.raw_connection()
        
    def cursor(self):
        return CloudCursor(self.conn.cursor())
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()

# The Secret Sauce: We hijack the local sqlite library to route directly to the cloud!
sqlite3.connect = lambda *args, **kwargs: CloudConnection()

# 2. Database Helper Function
def verify_login(username, password):
    conn = sqlite3.connect('registry_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, role FROM Users WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

# 3. Initialize Memory (Session State)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_name = ""
    st.session_state.user_role = ""

# 4. The login screen page with interactive UI.
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

# 5. The main dashboard UI screen.
else:
    st.sidebar.title(f"Welcome, {st.session_state.user_name}")
    st.sidebar.write(f"Role: **{st.session_state.user_role}**")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.clear()
        st.rerun()

    # A reset button option to cleanly rebuild the database, only available to the Admin(Registry).
    st.sidebar.divider()
    if st.sidebar.button("🚨 Reset Database to Default"):
        import os
        # 1. Delete the current messy database
        if os.path.exists('registry_database.db'):
            os.remove('registry_database.db')
        
        # When the user logs out the app will restart.
        st.session_state.clear()
        
        # 3. This reloads the page and triggers the excel seeder at the top of the page.
        st.rerun()
        
    # This section is a feature that allows the users to update their password whenever they feel like it.
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

    
    
    # This section is the whole registry dashboard with all its features within it.
    def registry_dashboard():
        st.title("🛡️ Registry Officer Dashboard")
        
        # FIXED: Swapped SQLite for Cloud Database
        conn = cloud_engine.raw_connection()
        
        try:
            # Added double quotes to table names for Postgres Case-Sensitivity
            remarks_df = pd.read_sql_query("""
                SELECT r.remark_id, u.name as "Lecturer Name", r.remark_text as "Remark", r.submit_date as "Date"
                FROM "Lecturer_Remarks" r
                JOIN "Users" u ON r.user_id = u.user_id
                WHERE r.status = 'Unread'
            """, conn)

            if not remarks_df.empty:
                with st.expander("🔔 FLAG: Unread Staff Remarks (Action Required)", expanded=True):
                    st.dataframe(remarks_df, hide_index=True, use_container_width=True)
                
                    with st.form("clear_remark_form"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            ack_id = st.selectbox("Select Remark ID to clear", remarks_df['remark_id'])
                        with col2:
                            st.write("") 
                            st.write("")
                            if st.form_submit_button("Acknowledge & Clear"):
                                cursor = conn.cursor()
                                # FIXED: Postgres '%s' syntax
                                cursor.execute('UPDATE "Lecturer_Remarks" SET status = \'Read\' WHERE remark_id = %s', (ack_id,))
                                conn.commit()
                                st.success("Remark cleared from dashboard!")
                                st.rerun()
                                
        except Exception as e:
            st.error(f"Error loading remarks: {e}")
            
        conn.close()
    
        st.divider()
        
        # Building the tabs within the registry dashboard.
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["Manage Users", "Manage Modules", "Semester Timetable", "Allocations Overview", "Promotions & Rotations"])
        
        with tab1:
            st.subheader("Current System Users")
            
            conn = cloud_engine.raw_connection()
            
            # --- THE FIX 1: Added 'department' and 'hire_year' to the main display table ---
            users_df = pd.read_sql_query('''
                SELECT user_id as "ID", name as "Full Name", username as "Username", department as "Department", role as "Role", title as "Title", research_status as "Research Status", hire_year as "Hire Year" 
                FROM "Users"
                ORDER BY "ID" ASC
            ''', conn)
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- FETCH AVAILABLE DEPARTMENTS ---
            # Dynamically grab any existing departments from the database to populate our dropdowns
            dept_df = pd.read_sql_query('''
                SELECT DISTINCT department FROM "Modules" WHERE department IS NOT NULL AND department != ''
                UNION 
                SELECT DISTINCT department FROM "Users" WHERE department IS NOT NULL AND department != ''
            ''', conn)
            available_depts = ["Unassigned"] + sorted([d for d in dept_df['department'].tolist() if d and d != "Unassigned"])

            # This section allows the Admin to edit and delete Users within the database.
            st.subheader("Edit or Delete Staff")
            
            # 1. First check if the database is completely empty
            if users_df.empty:
                st.info("No staff members found. Please use the Bulk Import tab to add staff!")
                st.stop() 

            # This creates a drop down user list also listing the names of the users with their id.
            user_list = users_df['ID'].astype(str) + " - " + users_df['Full Name']
            selected_user_str = st.selectbox("Select User to Modify", user_list)

            # 3. Get the ID 
            selected_id = int(selected_user_str.split(" - ")[0])
            
            # Grab that specific user's current data to fill the default values
            current_data = users_df[users_df['ID'] == selected_id].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                edit_name = st.text_input("Update Full Name", value=current_data['Full Name'])
                
                raw_user = current_data.get('Username')
                safe_username = "" if pd.isna(raw_user) else str(raw_user)
                edit_username = st.text_input("Update Username (Login ID)", value=safe_username)
                
                roles = ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor", "HoD", "HoS", "Registry Officer"]
                current_role = current_data['Role']
                role_index = roles.index(current_role) if current_role in roles else 0
                edit_role = st.selectbox("Update Role", roles, index=role_index)
                
                # --- THE FIX 2: Added the Department Dropdown to the Edit Form ---
                current_dept = current_data.get('Department')
                safe_dept = str(current_dept) if pd.notna(current_dept) else "Unassigned"
                if safe_dept not in available_depts:
                    available_depts.append(safe_dept) # Ensure no crash if current dept isn't in standard list
                dept_index = available_depts.index(safe_dept)
                edit_dept = st.selectbox("Update Department", available_depts, index=dept_index)
                
            with col2:
                raw_title = current_data.get('Title')
                safe_title = "" if pd.isna(raw_title) else str(raw_title)
                edit_title = st.text_input("Update Title (e.g., Dr, Mr, Prof)", value=safe_title)
                
                research_options = ["Satisfactory", "Unsatisfactory", "N/A"]
                raw_research = current_data.get('Research Status')
                safe_research = str(raw_research) if pd.notna(raw_research) else "Unsatisfactory"
                res_index = research_options.index(safe_research) if safe_research in research_options else 1
                edit_research = st.selectbox("Update Research Status", research_options, index=res_index)
                
                # --- THE FIX 3: Added Hire Year to the Edit Form ---
                raw_hire = current_data.get('Hire Year')
                current_yr = datetime.datetime.now().year
                safe_hire = int(raw_hire) if pd.notna(raw_hire) else current_yr
                edit_hire_year = st.number_input("Update Year Hired", min_value=1990, max_value=current_yr, value=safe_hire)
                
                # This is a feature that allows a password reset incase they forget their password.
                edit_password = st.text_input("Reset Password (leave blank to keep current)", type="password")
                
            st.write("Actions:")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("Update User", use_container_width=True):
                    cursor = conn.cursor()
                    # --- THE FIX 4: Added department and hire_year to the SQL UPDATE queries ---
                    if edit_password: 
                        cursor.execute('''UPDATE "Users" 
                                          SET name=%s, username=%s, role=%s, title=%s, research_status=%s, department=%s, hire_year=%s, password=%s 
                                          WHERE user_id=%s''', 
                                       (edit_name, edit_username, edit_role, edit_title, edit_research, edit_dept, edit_hire_year, edit_password, selected_id))
                    else: 
                        cursor.execute('''UPDATE "Users" 
                                          SET name=%s, username=%s, role=%s, title=%s, research_status=%s, department=%s, hire_year=%s 
                                          WHERE user_id=%s''', 
                                       (edit_name, edit_username, edit_role, edit_title, edit_research, edit_dept, edit_hire_year, selected_id))
                    conn.commit()
                    st.success(f"User updated successfully!")
                    st.rerun()
                    
            with btn_col2:
                if st.button("Delete User", type="primary", use_container_width=True):
                    if selected_id == 1:
                        st.error("Security Alert: You cannot delete the master Super Admin account!")
                    else:
                        cursor = conn.cursor()
                        cursor.execute('DELETE FROM "Users" WHERE user_id=%s', (selected_id,))
                        cursor.execute('DELETE FROM "Allocations" WHERE user_id=%s', (selected_id,))
                        conn.commit()
                        st.warning(f"User deleted from system!")
                        st.rerun()

            st.divider()
            
            # This section is to be able to manually add a new user providing all necessary informations within each field box.
            st.subheader("Register New Staff Member")
            with st.form("add_user_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    new_name = st.text_input("Full Name")
                    new_username = st.text_input("Username (Login ID)")
                    new_role = st.selectbox("Role", ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor", "HoD", "HoS", "Registry Officer"])
                    new_title = st.text_input("Title (Optional - e.g., Dr, Mr, Prof)")
                with col2:
                    new_research = st.selectbox("Research Performance", ["Satisfactory", "Unsatisfactory", "N/A"], index=1)
                    
                    new_dept = st.selectbox("Assign Department", available_depts)
                    
                    # This section is to manually insert the hire year of a specific user.
                    current_yr = datetime.datetime.now().year
                    new_hire_year = st.number_input("Year Hired", min_value=1990, max_value=current_yr, value=current_yr)
                    new_pass = st.text_input("Temporary Password", type="password")

                submit_user = st.form_submit_button("Create Account")

                if submit_user:
                    if new_name and new_username and new_pass:
                        cursor = conn.cursor()
                        cursor.execute('''INSERT INTO "Users" 
                                          (name, username, role, title, research_status, department, password, hire_year) 
                                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''', 
                                       (new_name, new_username, new_role, new_title, new_research, new_dept, new_pass, new_hire_year))
                        conn.commit()
                        st.success(f"Account created for {new_name} in {new_dept}!")
                        st.rerun()
                    else:
                        st.error("Please fill out the Name, Username, and Password fields.")
            
            st.divider()
            # This is the rectangular box where you can drag and drop files that needs to be imported on the database.
            st.subheader("📥 Bulk Import Staff (Annex Upload)")
            uploaded_file = st.file_uploader("Upload staff list (CSV or Excel)", type=['csv', 'xlsx'])

            if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        import_df = pd.read_csv(uploaded_file)
                    else:
                        import_df = pd.read_excel(uploaded_file)
                        
                    st.write("Preview of uploaded document:")
                    st.dataframe(import_df.head(3))

                    if st.button("Process & Import Users"):
                        cursor = conn.cursor()
                        added_count = 0
                        skipped_count = 0

                        for index, row in import_df.iterrows():
                            staff_name = str(row.get('Name', '')).strip()
                            staff_role = str(row.get('Role', '')).strip()
                            
                            staff_dept = str(row.get('Department', 'Unassigned')).strip()
                            if staff_dept == 'nan' or not staff_dept:
                                staff_dept = 'Unassigned'

                            if staff_name and staff_name != 'nan':
                                cursor.execute('SELECT * FROM "Users" WHERE name=%s', (staff_name,))
                                if not cursor.fetchone():
                                    cursor.execute('''INSERT INTO "Users" (name, role, research_status, department, password) 
                                                      VALUES (%s, %s, %s, %s, %s)''',
                                                   (staff_name, staff_role, 'Unsatisfactory', staff_dept, 'welcome123'))
                                    added_count += 1
                                else:
                                    skipped_count += 1 

                        conn.commit()

                        if added_count > 0:
                            st.success(f"✅ Successfully imported {added_count} new users! (Skipped {skipped_count} duplicates)")
                        else:
                            st.warning(f"⚠️ No new users added. All {skipped_count} people were already in the system.")

                except Exception as e:
                    st.error(f"Could not read the file. Error: {e}")
                    
            conn.close()

        with tab2:
            st.subheader("University Modules Database")
            
            # 1. FIXED: Connect to Cloud Database
            conn = cloud_engine.raw_connection()
            modules_df = pd.read_sql_query('SELECT * FROM "Modules"', conn)
            
            # To properly match the UTM timetable columns names, I had to rename the already written column names in the database.
            display_df = modules_df.rename(columns={
                'module_code': 'Module Code',
                'module_name': 'Module Name',
                'duration': 'Duration (Weeks)',
                'lecture_hours': 'Lecture Hrs',
                'tutorial_hours': 'Tutorial Hrs',
                'practical_hours': 'Practical Hrs'
            })
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ==========================================
            # EDIT OR DELETE MODULE SECTION
            # ==========================================
            st.subheader("Edit or Delete Module")
            
            if not modules_df.empty:
                module_list = modules_df['module_code'].astype(str) + " - " + modules_df['module_name']
                selected_mod_str = st.selectbox("Select Module to Modify", module_list)
                
                if selected_mod_str:
                    selected_mod_id = selected_mod_str.split(" - ")[0]
                    current_mod_data = modules_df[modules_df['module_code'] == selected_mod_id].iloc[0]
                    
                    # --- FIXED: Safely extract new data, handling NULLs ---
                    safe_dept = "" if pd.isna(current_mod_data.get('department')) else str(current_mod_data.get('department'))
                    safe_prog = "" if pd.isna(current_mod_data.get('programme')) else str(current_mod_data.get('programme'))
                    safe_coord = "" if pd.isna(current_mod_data.get('programme_coordinator')) else str(current_mod_data.get('programme_coordinator'))
                    safe_cred = 0 if pd.isna(current_mod_data.get('credits')) else int(current_mod_data.get('credits'))
                    safe_weight = 100.0 if pd.isna(current_mod_data.get('weightage')) else float(current_mod_data.get('weightage'))
                    
                    st.info(f"Editing Module Code: **{selected_mod_id}**")
                    
                    # --- FIXED: 3-Column Layout with ALL fields ---
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        edit_m_name = st.text_input("Update Module Name", value=current_mod_data['module_name'])
                        
                        raw_dur = current_mod_data.get('duration')
                        default_dur = 12 if pd.isna(raw_dur) else int(raw_dur)
                        edit_duration = st.number_input("Update Duration (Weeks)", min_value=1, value=default_dur)
                        
                        edit_dept = st.text_input("Department", value=safe_dept)
                        edit_prog = st.text_input("Programme", value=safe_prog)
                        
                    with col2:
                        edit_l_hrs = st.number_input("Update Lecture Hours (L)", min_value=0, value=int(current_mod_data.get('lecture_hours', 3)))
                        edit_t_hrs = st.number_input("Update Tutorial Hours (T)", min_value=0, value=int(current_mod_data.get('tutorial_hours', 0)))
                        edit_p_hrs = st.number_input("Update Practical Hours (P)", min_value=0, value=int(current_mod_data.get('practical_hours', 0)))
                        
                    with col3:
                        edit_coord = st.text_input("Programme Coordinator", value=safe_coord)
                        edit_cred = st.number_input("Credits", value=safe_cred)
                        edit_weight = st.number_input("Weightage (%)", value=safe_weight)
                        
                    st.write("Actions:")
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Update Module", use_container_width=True):
                            cursor = conn.cursor()
                            # FIXED: Postgres Syntax and all 11 columns
                            cursor.execute('''
                                UPDATE "Modules" 
                                SET module_name=%s, duration=%s, lecture_hours=%s, tutorial_hours=%s, practical_hours=%s, 
                                    department=%s, programme=%s, programme_coordinator=%s, credits=%s, weightage=%s
                                WHERE module_code=%s
                            ''', (edit_m_name, edit_duration, edit_l_hrs, edit_t_hrs, edit_p_hrs, edit_dept, edit_prog, edit_coord, edit_cred, edit_weight, selected_mod_id))
                            conn.commit()
                            st.success("Module updated successfully!")
                            st.rerun()
                            
                    with btn_col2:
                        if st.button("Delete Module", type="primary", use_container_width=True):
                            cursor = conn.cursor()
                            cursor.execute('DELETE FROM "Modules" WHERE module_code=%s', (selected_mod_id,))
                            cursor.execute('DELETE FROM "Allocations" WHERE module_code=%s', (selected_mod_id,))
                            conn.commit()
                            st.warning("Module deleted from system!")
                            st.rerun()

            st.divider()
            
            # ==========================================
            # IMPORT SEMESTER TIMETABLE SECTION
            # ==========================================
            st.subheader("📅 Import Semester Timetable")
            st.info("Upload the official UTM Semester Timetable to automatically extract metadata and update records.")
            
            uploaded_file = st.file_uploader("Upload Official Timetable (Excel)", type=["xlsx", "xls"], key="module_uploader")
            
            if uploaded_file is not None:
                try:
                    cursor = conn.cursor()
                    
                    # --- 1. EXTRACT 7-ROW METADATA ---
                    meta_df = pd.read_excel(uploaded_file, header=None, nrows=7)
                    
                    # --- THE NEW BOUNCER (Graceful Exception) ---
                    if len(meta_df) < 7:
                        raise ValueError("The uploaded file does not match the Official UTM Timetable format. Missing the 7-row header.")
                        
                    uni_name = str(meta_df.iloc[0, 0]).strip()
                    faculty_name = str(meta_df.iloc[1, 0]).strip()
                    acad_year = str(meta_df.iloc[2, 0]).strip()
                    start_date = str(meta_df.iloc[3, 0]).strip()
                    exemption_date = str(meta_df.iloc[4, 0]).strip()
                    end_dates = str(meta_df.iloc[5, 0]).strip()
                    venue_notes = str(meta_df.iloc[6, 0]).strip()
                    
                    # Save the metadata to the database
                    cursor.execute('''
                        INSERT INTO "Semester_Metadata" 
                        (university, faculty, academic_year, start_date, exemption_date, end_dates, venue_notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (uni_name, faculty_name, acad_year, start_date, exemption_date, end_dates, venue_notes))
                    conn.commit()

                    # Display the extracted metadata beautifully on the dashboard
                    st.success("✅ Semester Metadata Successfully Extracted & Saved!")
                    with st.expander("View Detected Semester Details", expanded=True):
                        st.markdown(f"""
                        * **Institution:** {uni_name} ({faculty_name})
                        * **Academic Term:** {acad_year}
                        * **{start_date}**
                        * **{end_dates}**
                        """)

                    # --- 2. LOAD THE TIMETABLE DATA ---
                    mod_df = pd.read_excel(uploaded_file, header=8)
                    col_code = 'Module Code'
                    col_name = 'Module Title'
                    col_prog = 'Programme'
                    col_coord = 'PROGRAMME COORDINATOR'
                    col_weight = 'Weightage'
                    
                    st.write("### File Preview:")
                    st.dataframe(mod_df.head())
                        
                    required_cols = [col_code, col_name]
                    missing_cols = [col for col in required_cols if col not in mod_df.columns]
                    
                    if missing_cols:
                        st.error(f"⚠️ Your file is missing these required columns: {', '.join(missing_cols)}")
                    else:
                        if st.button("Run Timetable Import", type="primary"):
                            import_count = 0
                            alloc_count = 0
                            
                            # Wipe the old timetable data so we don't get duplicates on re-upload
                            cursor.execute('DELETE FROM "Class_Schedules"')
                            
                            for index, row in mod_df.iterrows():
                                code = str(row.get(col_code, '')).strip()
                                name = str(row.get(col_name, '')).strip()
                                
                                if code == 'nan' or code == '' or pd.isna(row.get(col_code)): continue
                                
                                # --- NEW FIX: Extract Department ---
                                raw_dept = str(row.get('Dept', 'Unassigned')).strip()
                                dept = raw_dept if raw_dept != 'nan' and raw_dept != '' else 'Unassigned'

                                # 1. --- MODULE DATA ---
                                prog = str(row.get(col_prog, 'General')).strip()
                                coord = str(row.get(col_coord, 'Unassigned')).strip()
                                
                                try: weight = float(row.get(col_weight, 0))
                                except: weight = 0.0
                                
                                try: duration = int(row.get('Semester Duration (15 / 12 Weeks)', 15))
                                except: duration = 15
                                
                                try: hours = int(row.get('Lecture Hours (L)', 3))
                                except: hours = 3
                                
                                cursor.execute('SELECT * FROM "Modules" WHERE module_code=%s', (code,))
                                if cursor.fetchone():
                                    cursor.execute('''UPDATE "Modules" SET 
                                        module_name=%s, duration=%s, lecture_hours=%s, department=%s, programme=%s, programme_coordinator=%s, weightage=%s WHERE module_code=%s''', 
                                        (name, duration, hours, dept, prog, coord, weight, code))
                                else:
                                    cursor.execute('''INSERT INTO "Modules" 
                                        (module_code, module_name, duration, lecture_hours, department, programme, programme_coordinator, weightage) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''', 
                                        (code, name, duration, hours, dept, prog, coord, weight))
                                        
                                # 2. --- SCHEDULE DATA ---
                                cohort = str(row.get('Cohort', '')).strip()
                                
                                # Safely grab student numbers
                                try: students = int(row.get('No. of Students', 0))
                                except: students = 0
                                
                                # The Excel column headers have exact spacing/newlines we must match
                                raw_resource = str(row.get('Resource Person\nSURNAME Name (Title)', '')).strip()
                                ft_pt = str(row.get('FT/PT', '')).strip()
                                f2f = str(row.get('Face to Face\n(Odd / Even Weeks?) ', '')).strip()
                                online = str(row.get('Online Sessions\n(Odd / Even Weeks?) ', '')).strip()
                                day = str(row.get('Day', '')).strip()
                                time = str(row.get('Time ', '')).strip()
                                venue = str(row.get('Venue', '')).strip()
                                
                                # Only insert into Class_Schedules if there is actual scheduling info
                                if day != 'nan' and day != '':
                                    cursor.execute('''
                                        INSERT INTO "Class_Schedules"
                                        (module_code, cohort, no_of_students, resource_person, ft_pt, face_to_face_weeks, online_sessions_weeks, day_of_week, time_slot, venue)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ''', (code, cohort, students, raw_resource, ft_pt, f2f, online, day, time, venue))
                                
                                # 3. --- SMART AUTO-ALLOCATION & ROLE INFERENCE ---
                                if raw_resource != 'nan' and raw_resource != '':
                                    # Properly extract Title and Staff Name
                                    title = ""
                                    staff_name = raw_resource
                                    if "(" in raw_resource and ")" in raw_resource:
                                        title = raw_resource.split("(")[1].split(")")[0].strip()
                                        staff_name = raw_resource.split("(")[0].strip()
                                    
                                    # Parse the Semester from the "Level Sem" column
                                    level_sem_raw = str(row.get('Level Sem\ne.g L1S2', '')).upper()
                                    target_semester = "Semester 2" if 'S2' in level_sem_raw else "Semester 1"
                                    
                                    # Find the user in the PostgreSQL database
                                    cursor.execute('SELECT user_id FROM "Users" WHERE name ILIKE %s', (f"%{staff_name}%",))
                                    user_match = cursor.fetchone()
                                    
                                    # --- AUTO-CREATE MISSING USERS WITH INTELLIGENT MAPPING ---
                                    # First, calculate what Role they SHOULD have based on the Excel file
                                    inferred_role = "Lecturer"
                                    raw_upper = raw_resource.upper()
                                    
                                    if "ASSOC PROF" in raw_upper or "AP" in raw_upper:
                                        inferred_role = "Associate Professor"
                                    elif "PROF" in raw_upper:
                                        inferred_role = "Professor"
                                    elif "(DR)" in raw_upper:
                                        inferred_role = "HoD" 

                                    if not user_match:
                                        # SCENARIO A: User is totally new. CREATE THEM.
                                        default_username = staff_name.lower().replace(" ", ".")
                                        default_password = "password123" 
                                        
                                        # --- THE FIX: Removed category_level, ADDED department ---
                                        cursor.execute('''
                                            INSERT INTO "Users" (username, password, name, role, title, department) 
                                            VALUES (%s, %s, %s, %s, %s, %s)
                                        ''', (default_username, default_password, staff_name, inferred_role, title, dept))
                                        conn.commit() 
                                        
                                        cursor.execute('SELECT user_id FROM "Users" WHERE name=%s', (staff_name,))
                                        user_match = cursor.fetchone()
                                        st.toast(f"Created new user: {staff_name} as {inferred_role} in {dept}") 
                                        
                                    else:
                                        # SCENARIO B: User already exists! UPDATE THEM.
                                        s_id = user_match[0]
                                        
                                        # Check if they already have a department assigned manually
                                        cursor.execute('SELECT department FROM "Users" WHERE user_id=%s', (s_id,))
                                        curr_dept_row = cursor.fetchone()
                                        curr_dept = curr_dept_row[0] if curr_dept_row else None
                                        
                                        if not curr_dept or curr_dept == 'Unassigned':
                                            cursor.execute('''
                                                UPDATE "Users" 
                                                SET role=%s, title=%s, department=%s
                                                WHERE user_id=%s
                                            ''', (inferred_role, title, dept, s_id))
                                        else:
                                            cursor.execute('''
                                                UPDATE "Users" 
                                                SET role=%s, title=%s 
                                                WHERE user_id=%s
                                            ''', (inferred_role, title, s_id))
                                        conn.commit()

                                    # Finally, log the allocation mapping
                                    if user_match:
                                        s_id = user_match[0]
                                        cursor.execute('SELECT * FROM "Allocations" WHERE user_id=%s AND module_code=%s AND level_semester=%s AND semester=%s', 
                                                       (s_id, code, cohort, target_semester))
                                        if not cursor.fetchone():
                                            cursor.execute('INSERT INTO "Allocations" (user_id, module_code, level_semester, semester) VALUES (%s, %s, %s, %s)', 
                                                           (s_id, code, cohort, target_semester))
                                            alloc_count += 1

                                import_count += 1
                                
                            conn.commit()
                                
                            st.success(f"✅ Successfully processed {import_count} modules and auto-assigned {alloc_count} workloads!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error processing file: {e}")
            
            st.divider()
            
            # ==========================================
            # MANUALLY ADD MODULE SECTION
            # ==========================================
            st.subheader("Manually Add a Module")
            with st.form("add_module_form", clear_on_submit=True):
                # --- FIXED: 3-Column layout with all 11 fields ---
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    m_id = st.text_input("Module Code (e.g., SE101)")
                    m_name = st.text_input("Module Name")
                    m_dept = st.text_input("Department")
                    m_prog = st.text_input("Programme")
                    
                with col2:
                    m_duration = st.number_input("Duration (Weeks)", min_value=1, value=15)
                    l_hrs = st.number_input("Lecture Hours (L)", min_value=0, value=0)
                    t_hrs = st.number_input("Tutorial Hours (T)", min_value=0, value=0)
                    
                with col3:
                    p_hrs = st.number_input("Practical Hours (P)", min_value=0, value=0)
                    m_coord = st.text_input("Programme Coordinator")
                    m_cred = st.number_input("Credits", min_value=0, value=3)
                    m_weight = st.number_input("Weightage (%)", min_value=0.0, value=100.0)
                    
                submit_mod = st.form_submit_button("Save Module to Database")
                
                if submit_mod:
                    if m_id and m_name:
                        cursor = conn.cursor()
                        # FIXED: Postgres Syntax for all 11 columns
                        cursor.execute('''
                            INSERT INTO "Modules" 
                            (module_code, module_name, duration, lecture_hours, tutorial_hours, practical_hours, department, programme, programme_coordinator, credits, weightage) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (m_id, m_name, m_duration, l_hrs, t_hrs, p_hrs, m_dept, m_prog, m_coord, m_cred, m_weight))
                        conn.commit()
                        st.success(f"Module {m_id} successfully added!")
                        st.rerun()
                    else:
                        st.error("Module Code and Name are required.")
            
            conn.close()

        # ==========================================
        # TAB 3: SEMESTER TIMETABLE VIEWER
        # ==========================================
        with tab3:
            st.subheader("📅 Interactive Semester Timetable")
            st.info("Use the dropdown filters below to search for specific schedules.")
            
            conn = cloud_engine.raw_connection()
            try:
                # Grab all schedule data
                schedules_df = pd.read_sql_query('SELECT * FROM "Class_Schedules" ORDER BY day_of_week, time_slot', conn)
                
                if schedules_df.empty:
                    st.warning("No timetable data found in the database. Please run the Timetable Import in Tab 2.")
                else:
                    # --- DYNAMIC FILTERS ---
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        # Get a list of unique cohorts, removing empty strings/nan
                        cohort_list = sorted([c for c in schedules_df['cohort'].unique() if c and c != 'nan'])
                        cohort_filter = st.selectbox("Filter by Cohort", ["Show All"] + cohort_list)
                        
                    with col2:
                        lecturer_list = sorted([l for l in schedules_df['resource_person'].unique() if l and l != 'nan'])
                        lecturer_filter = st.selectbox("Filter by Lecturer", ["Show All"] + lecturer_list)
                        
                    with col3:
                        venue_list = sorted([v for v in schedules_df['venue'].unique() if v and v != 'nan'])
                        venue_filter = st.selectbox("Filter by Venue / Room", ["Show All"] + venue_list)

                    # --- APPLY FILTERS ---
                    filtered_df = schedules_df.copy()
                    
                    if cohort_filter != "Show All":
                        filtered_df = filtered_df[filtered_df['cohort'] == cohort_filter]
                    if lecturer_filter != "Show All":
                        filtered_df = filtered_df[filtered_df['resource_person'] == lecturer_filter]
                    if venue_filter != "Show All":
                        filtered_df = filtered_df[filtered_df['venue'] == venue_filter]

                    # --- DISPLAY DATA ---
                    st.write(f"**Found {len(filtered_df)} scheduled sessions:**")
                    
                    # Clean up the column names for the user UI
                    display_cols = {
                        'module_code': 'Module Code',
                        'cohort': 'Cohort',
                        'day_of_week': 'Day',
                        'time_slot': 'Time Slot',
                        'venue': 'Venue',
                        'resource_person': 'Lecturer Assigned',
                        'face_to_face_weeks': 'F2F Weeks',
                        'online_sessions_weeks': 'Online Weeks'
                    }
                    
                    # Display the beautiful filtered table
                    st.dataframe(filtered_df[list(display_cols.keys())].rename(columns=display_cols), use_container_width=True, hide_index=True)

            except Exception as e:
                st.error(f"Error loading timetable: {e}")
            finally:
                conn.close()

        # ==========================================
        # TAB 4: WORKLOAD & ALLOCATIONS OVERVIEW
        # ==========================================
        with tab4:
            st.subheader("Workload & Allocations Overview")
            
            # FIXED: Cloud Database Connection
            conn = cloud_engine.raw_connection()
            
            # Two semester tracking feature.
            selected_semester = st.radio("⏳ Select Active Semester to View:", ["Semester 1", "Semester 2"], horizontal=True)
            st.divider()
            
            # This is the smart workload calculator
            st.markdown(f"### Lecturer Workload Analysis ({selected_semester})")
            st.info("💡 Workload limits are accurately calculated based on Role and Research Performance (Annex Guidelines).")
            
            # --- THE FIX 1: Fetching 'research_status' alongside the module count ---
            workload_query = '''
                SELECT u.name as "Lecturer", u.role as "Role", u.research_status as "Research_Status", COUNT(a.module_code) as "Assigned Modules"
                FROM "Users" u
                LEFT JOIN "Allocations" a ON u.user_id = a.user_id AND a.semester = %s
                WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')
                GROUP BY u.user_id, u.name, u.role, u.research_status
            '''
            
            try:
                workload_df = pd.read_sql_query(workload_query, conn, params=(selected_semester,))
                
                # --- THE FIX 2: Advanced Annex-Based Limit Calculator ---
                def calculate_limits(row):
                    role = row['Role']
                    # Safely handle missing research status just in case
                    research = str(row['Research_Status']).strip() if pd.notna(row['Research_Status']) else "Unsatisfactory"
                    
                    normal, excess_sat, excess_unsat = 0, 0, 0
                    
                    if role == "HoS":
                        normal, excess_sat, excess_unsat = 2, 4, 2
                    elif role == "HoD":
                        normal, excess_sat, excess_unsat = 4, 4, 2
                    elif role in ["Professor", "Associate Professor"]: 
                        normal, excess_sat, excess_unsat = 5, 4, 2
                    elif role == "Senior Lecturer":                    
                        normal, excess_sat, excess_unsat = 5, 2, 1
                    elif role == "Lecturer":                           
                        normal, excess_sat, excess_unsat = 6, 6, 3
                
                    # Calculate their specific max limit based on their research status
                    allowed_excess = excess_sat if research == "Satisfactory" else excess_unsat
                    max_allowed = normal + allowed_excess
                    
                    return pd.Series([normal, allowed_excess, max_allowed])
                
                # Apply the math to the dataframe
                workload_df[['Normal Quantum', 'Allowed Excess', 'Absolute Max']] = workload_df.apply(calculate_limits, axis=1)
                
                # --- THE FIX 3: 3-Tier Status Calculation (Normal, Excess, Overload) ---
                workload_df['Overload'] = workload_df['Assigned Modules'] - workload_df['Absolute Max']
                workload_df['Overload'] = workload_df['Overload'].apply(lambda x: x if x > 0 else 0)
                
                def get_status(r):
                    if r['Overload'] > 0: return "🚨 OVERLOAD"
                    if r['Assigned Modules'] > r['Normal Quantum']: return "⚠️ EXCESS"
                    return "✅ NORMAL"
                    
                workload_df['Status'] = workload_df.apply(get_status, axis=1)
                
                # Highlight Overloaded rows in Red, and Excess rows in Yellow
                def highlight_status(row):
                    if row['Overload'] > 0:
                        return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
                    elif row['Assigned Modules'] > row['Normal Quantum']:
                        return ['background-color: rgba(255, 215, 0, 0.2)'] * len(row)
                    return [''] * len(row)
    
                # Reorder columns for a clean, professional display
                display_cols = ['Lecturer', 'Role', 'Research_Status', 'Assigned Modules', 'Normal Quantum', 'Allowed Excess', 'Absolute Max', 'Overload', 'Status']
                final_df = workload_df[display_cols].rename(columns={'Research_Status': 'Research Status'})
                
                styled_df = final_df.style.apply(highlight_status, axis=1)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Error loading workload analytics: {e}")
            
            st.divider()
            
            # ==========================================
            # Detailed master list
            # ==========================================
            st.markdown(f"### Detailed Master List ({selected_semester})")
            
            all_data = pd.read_sql_query('''
                SELECT u.name as "Lecturer", a.module_code as "Module Code", m.module_name as "Module Title", a.level_semester as "Cohort/Group", a.semester as "Semester"
                FROM "Allocations" a
                JOIN "Users" u ON a.user_id = u.user_id
                JOIN "Modules" m ON a.module_code = m.module_code
                WHERE a.semester = %s
            ''', conn, params=(selected_semester,))
            
            lecturer_options = ["All Lecturers"] + sorted(all_data['Lecturer'].unique().tolist()) if not all_data.empty else ["All Lecturers"]
            selected_filter = st.selectbox("🔍 Search / Filter by Lecturer", lecturer_options)
            
            if selected_filter != "All Lecturers":
                display_data = all_data[all_data['Lecturer'] == selected_filter]
            else:
                display_data = all_data
                
            st.caption(f"Showing **{len(display_data)}** assigned module(s) for {selected_semester}.")
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
            st.divider()

            # ==========================================
            # Manual Assignment Control
            # ==========================================
            st.markdown("### Manual Assignment Control")
            
            if 'saved_staff_index' not in st.session_state:
                st.session_state.saved_staff_index = 0
                
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Assign a Module to Staff**")
                
                with st.form("assign_form"):
                    staff_df = pd.read_sql_query('''SELECT user_id, name FROM "Users" WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')''', conn)
                    
                    if staff_df.empty:
                        st.warning("⚠️ No teaching staff found.")
                        st.form_submit_button("Assign Module", disabled=True)
                    else:
                        staff_list = (staff_df['user_id'].astype(str) + " - " + staff_df['name']).tolist()
                        
                        if st.session_state.saved_staff_index >= len(staff_list):
                            st.session_state.saved_staff_index = 0
                            
                        selected_staff = st.selectbox("Select Staff Member", staff_list, index=st.session_state.saved_staff_index)
                        mod_df = pd.read_sql_query('SELECT module_code, module_name FROM "Modules"', conn)
                        
                        if mod_df.empty:
                            st.warning("⚠️ No modules found.")
                            st.form_submit_button("Assign Module", disabled=True)
                        else:
                            mod_list = mod_df['module_code'].astype(str) + " - " + mod_df['module_name']
                            selected_mod = st.selectbox("Select Module", mod_list)
                            
                            col_a, col_b = st.columns(2)
                            with col_a:
                                assign_semester = st.selectbox("Target Semester", ["Semester 1", "Semester 2"], index=0 if selected_semester == "Semester 1" else 1)
                            with col_b:
                                assign_cohort = st.text_input("Cohort / Group", value="Group A")
                            
                            submit_assign = st.form_submit_button("Assign Module", use_container_width=True)
                            
                            if submit_assign:
                                st.session_state.saved_staff_index = staff_list.index(selected_staff)
                                s_id = int(selected_staff.split(" - ")[0])
                                m_id = selected_mod.split(" - ")[0]
                                
                                cursor = conn.cursor()
                                cursor.execute('SELECT * FROM "Allocations" WHERE user_id=%s AND module_code=%s AND level_semester=%s AND semester=%s', (s_id, m_id, assign_cohort, assign_semester))
                                if cursor.fetchone():
                                    st.error(f"This person is already teaching {m_id} for {assign_cohort} in {assign_semester}!")
                                else:
                                    cursor.execute('INSERT INTO "Allocations" (user_id, module_code, level_semester, semester) VALUES (%s, %s, %s, %s)', (s_id, m_id, assign_cohort, assign_semester))
                                    conn.commit()
                                    st.success(f"Assigned {m_id} ({assign_cohort}) to {assign_semester} successfully!")
                                    st.rerun()

            with col2:
                st.write("**Remove an Allocation**")
                with st.form("remove_form"):
                    alloc_df = pd.read_sql_query('''
                        SELECT a.user_id, u.name, a.module_code, m.module_name, a.level_semester, a.semester
                        FROM "Allocations" a
                        JOIN "Users" u ON a.user_id = u.user_id
                        JOIN "Modules" m ON a.module_code = m.module_code
                    ''', conn)
                    
                    if not alloc_df.empty:
                        alloc_list = alloc_df['user_id'].astype(str) + "|" + alloc_df['module_code'] + "|" + alloc_df['level_semester'] + "|" + alloc_df['semester'] + " : " + alloc_df['name'] + " - " + alloc_df['module_name'] + " (" + alloc_df['level_semester'] + ", " + alloc_df['semester'] + ")"
                        selected_alloc = st.selectbox("Select Assignment to Remove", alloc_list)
                        
                        submit_remove = st.form_submit_button("Remove Allocation", type="primary", use_container_width=True)
                        
                        if submit_remove:
                            keys = selected_alloc.split(" : ")[0].split("|")
                            r_uid, r_mid, r_cohort, r_semester = int(keys[0]), keys[1], keys[2], keys[3]
                            
                            cursor = conn.cursor()
                            cursor.execute('DELETE FROM "Allocations" WHERE user_id=%s AND module_code=%s AND level_semester=%s AND semester=%s', (r_uid, r_mid, r_cohort, r_semester))
                            conn.commit()
                            st.success("Allocation removed successfully!")
                            st.rerun()
                    else:
                        st.info("There are no allocations to remove.")
                        st.form_submit_button("Remove Allocation", disabled=True)

            conn.close()

        # ==========================================
        #         TAB 5: PROMOTION MANAGEMENT
        # ==========================================
        with tab5:
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
                           COUNT(a.module_code) as "Active Modules"
                    FROM Users u
                    LEFT JOIN Allocations a ON u.user_id = a.user_id
                    WHERE u.category_level IN ('Category 5 (Other Academic)', 'Category 4 (PhD Staff)')
                    GROUP BY u.user_id, u.name, u.role, u.category_level, u.hire_year
                    HAVING (2026 - u.hire_year) >= 3 AND COUNT(a.module_code) >= 2
                """, conn)
                
                if radar_df.empty:
                    st.info("No staff currently meet the baseline eligibility criteria.")
                else:
                    st.dataframe(radar_df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Error loading radar: {e}")

            st.divider()

            # --- PART 2: THE VERIFICATION QUEUE & LETTERS ---
            st.subheader("📥 Application Verification Queue")
            st.write("Review registration letters and forward verified applications to the respective Department Heads.")

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
                    st.success("✅ No new promotion applications require forwarding at this time.")
                else:
                    st.dataframe(queue_df, use_container_width=True, hide_index=True)
                    st.divider()

                    # --- NEW: REVIEW APPLICATION LETTER ---
                    st.write("### 📄 Step 1: Review Registration Letter")
                    view_ticket = st.selectbox("Select Ticket ID to Download Letter:", queue_df['ticket_id'], key="reg_letter_select")
                    
                    cursor = conn.cursor()
                    cursor.execute("SELECT u.name, p.registration_letter FROM Pending_Promotions p JOIN Users u ON p.user_id = u.user_id WHERE p.ticket_id = ?", (int(view_ticket),))
                    letter_data = cursor.fetchone()
                    
                    if letter_data and letter_data[1]:
                        applicant_name = letter_data[0]
                        pdf_bytes = letter_data[1]
                        
                        st.download_button(
                            label=f"📥 Download Registration Letter ({applicant_name})",
                            data=pdf_bytes,
                            file_name=f"Registration_Letter_{applicant_name.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            type="secondary"
                        )
                    else:
                        st.warning("⚠️ No registration letter is attached to this ticket.")
                        
                    st.divider()
                    
                    # --- NEW: VERIFICATION DECISION WITH REJECT LOGIC ---
                    st.write("### ✅ Step 2: Verification Decision")

                    with st.form("registry_verify_form"):
                        action = st.radio("Registry Decision", ["Verify & Forward to HoD", "Reject (Invalid/Missing Documents)"], horizontal=True)
                        rejection_reason = st.text_area("Rejection Reason (Required if Rejecting)", placeholder="e.g., The attached PDF is blurred or incorrect.")
                        
                        if st.form_submit_button("Submit Verification", type="primary", use_container_width=True):
                            if "Reject" in action and not rejection_reason.strip():
                                st.error("You must provide a reason for rejecting the document.")
                            else:
                                if "Verify" in action:
                                    # FIXED: Swapped ? for %s
                                    cursor.execute('UPDATE "Pending_Promotions" SET status = \'Pending HoD\', rejection_reason = \'\' WHERE ticket_id = %s', (view_ticket,))
                                    st.success(f"Ticket #{view_ticket} verified and forwarded to the HoD!")
                                else:
                                    # FIXED: Swapped ? for %s
                                    cursor.execute('UPDATE "Pending_Promotions" SET status = \'Rejected\', rejection_reason = %s WHERE ticket_id = %s', (rejection_reason, view_ticket))
                                    st.warning(f"Ticket #{view_ticket} has been rejected and sent back to the applicant.")
                                    
                                conn.commit()
                                st.rerun()

            except Exception as e:
                st.error(f"Error loading verification queue: {e}")
                
            conn.close()

        

    # --- LECTURER VIEW ---
    def lecturer_dashboard():
        st.title(f"👋 Welcome, {st.session_state.user_name}")
        
        # 1. FIXED: Connect to Cloud Database
        conn = cloud_engine.raw_connection()
        
        # --- NEW: FETCH PROFILE, DEPARTMENT & WORKLOAD ---
        cursor = conn.cursor()
        cursor.execute('SELECT role, research_status, department, hire_year FROM "Users" WHERE user_id = %s', (st.session_state.user_id,))
        user_info = cursor.fetchone()
        
        role = user_info[0] if user_info and user_info[0] else "Lecturer"
        research = user_info[1] if user_info and user_info[1] else "Unsatisfactory"
        dept = user_info[2] if user_info and user_info[2] else "Unassigned"
        hire_year = user_info[3] if user_info and user_info[3] else datetime.datetime.now().year
        
        # THE FIX: Displaying the Department & Research Status clearly in the profile banner!
        st.markdown(f"**Role:** {role} &nbsp;|&nbsp; **Department:** {dept} &nbsp;|&nbsp; **Research Status:** {research}")
        
        # FIXED: Postgres SQL syntax
        my_modules = pd.read_sql_query("""
            SELECT m.module_code as "Code", m.module_name as "Module Title", m.programme as "Programme", m.programme_coordinator as "Coordinator", m.weightage as "Weightage", m.lecture_hours as "L", m.tutorial_hours as "T", m.practical_hours as "P"
            FROM "Allocations" a
            JOIN "Modules" m ON a.module_code = m.module_code
            WHERE a.user_id = %s
        """, conn, params=(st.session_state.user_id,))
        
        current_yr = datetime.datetime.now().year
        years_served = current_yr - hire_year
        workload_count = len(my_modules)

        # --- TOP ROW: Quick Stats ---
        col1, col2, col3 = st.columns(3)
        col1.metric("Current Role", role)
        col2.metric("Teaching Load", f"{workload_count} Modules")
        col3.metric("Service Time", f"{years_served} Years")

        st.divider()

        # --- SECTION: UPGRADED PROMOTION MANAGEMENT ---
        st.subheader("🚀 Promotion Management")
        
        # 1. Check for ACTIVE tickets to see if we should hide the form
        cursor.execute("""
            SELECT COUNT(*) FROM "Pending_Promotions" 
            WHERE user_id = %s AND status NOT IN ('Approved', 'Rejected')
        """, (st.session_state.user_id,))
        active_tickets = cursor.fetchone()[0]
        
        # 2. Eligibility & Application Form (Only show if NO active tickets exist)
        if active_tickets == 0:
            if workload_count >= 3 and years_served >= 3:
                st.success("✅ You meet the baseline criteria to apply for a promotion!")
                
                with st.form("lecturer_promo_form"):
                    st.write("Submit your application to the Registry Office for verification:")
                    req_role = st.selectbox("Requested Title", ["Senior Lecturer", "Associate Professor", "Professor"])
                    req_category = st.selectbox("Requested Category", ["Category 1 (Management)", "Category 2 (Professional)", "Category 3 (Technical)", "Category 4 (PhD Staff)", "Category 5 (Other Academic)"])
                    
                    st.info("📄 Please attach your official Registration Letter to proceed.")
                    reg_letter = st.file_uploader("Upload Registration Letter (PDF only)", type=["pdf"])
                    
                    if st.form_submit_button("Submit Application"):
                        # Safety Catch: Block them if they forgot the PDF!
                        if reg_letter is None:
                            st.error("⚠️ You must upload your PDF Registration Letter to apply.")
                        else:
                            # Convert the PDF into raw binary data so it can live in the database
                            letter_bytes = reg_letter.read()
                            
                            cursor.execute('SELECT MAX(ticket_id) FROM "Pending_Promotions"')
                            max_id_result = cursor.fetchone()[0]
                            new_ticket_id = 1 if max_id_result is None else int(max_id_result) + 1
                            
                            # FIXED: Postgres SQL syntax
                            cursor.execute("""
                                INSERT INTO "Pending_Promotions" (ticket_id, user_id, proposed_role, proposed_category, status, rejection_reason, registration_letter)
                                VALUES (%s, %s, %s, %s, 'Pending Registry', '', %s)
                            """, (new_ticket_id, st.session_state.user_id, req_role, req_category, letter_bytes))
                            
                            conn.commit()
                            st.success("Application and Letter successfully submitted to the Registry Office!")
                            st.rerun()
            else:
                st.info("Keep up the great work! You are currently working toward promotion eligibility.")
        else:
            # If they have an active ticket, hide the form so they don't spam applications
            st.info("⏳ You currently have an active promotion application under review. Please wait for a final decision.")

        st.divider()

        # 3. Application History Tracker (Clean UI Version)
        st.write("### Application Status")
        cursor.execute("""
            SELECT ticket_id, proposed_role, proposed_category, status, rejection_reason 
            FROM "Pending_Promotions" 
            WHERE user_id = %s
            ORDER BY ticket_id DESC
        """, (st.session_state.user_id,))
        
        my_requests = cursor.fetchall()
        
        if not my_requests:
            st.write("No prior applications found on your record.")
        else:
            # Sort the tickets into two separate lists
            active_reqs = [req for req in my_requests if req[3] not in ('Approved', 'Rejected')]
            past_reqs = [req for req in my_requests if req[3] in ('Approved', 'Rejected')]
            
            # --- PROMINENT DISPLAY: Active Tickets ---
            if active_reqs:
                for req in active_reqs:
                    t_id, p_role, p_cat, status, rej_reason = req
                    with st.container(border=True):
                        st.markdown(f"**Ticket #{t_id} | Active Request:** {p_role} *( {p_cat} )*")
                        
                        if status == 'Pending Registry':
                            st.info("📋 **Current Status:** Awaiting Registry Verification")
                            st.progress(25)
                        elif status == 'Pending HoD':
                            st.warning("⏳ **Current Status:** Awaiting Department Head (HoD) Review")
                            st.progress(50)
                        elif status == 'Pending HoS':
                            st.info("🔍 **Current Status:** Awaiting Final Head of School (HoS) Approval")
                            st.progress(75)
                            
            # --- HIDDEN DISPLAY: The Archive Expander ---
            if past_reqs:
                # expanded=False ensures this stays closed and out of the way until clicked
                with st.expander("📂 View Past Applications & Official Feedback", expanded=False):
                    for req in past_reqs:
                        t_id, p_role, p_cat, status, rej_reason = req
                        with st.container(border=True):
                            st.markdown(f"**Ticket #{t_id} | Requested:** {p_role} *( {p_cat} )*")
                            
                            if status == 'Approved':
                                st.success("🎉 **Status:** Approved! Official title was updated.")
                            elif status == 'Rejected':
                                st.error("❌ **Status:** Rejected.")
                                st.write(f"**Official Feedback:** {rej_reason}")

        st.divider()

        # --- SECTION: Remarks for Registry ---
        st.subheader("💬 Registry Communications")
        with st.form("registry_remarks_form"):
            st.write("Submit a remark or flag an issue regarding your workload/modules directly to the Registry. (Maximum: 400 words)")
            
            # max_chars acts as a UI buffer (approx 400-500 words depending on word length)
            remark = st.text_area("Enter your remark here:", max_chars=2500)
            
            if st.form_submit_button("Send to Registry"):
                word_count = len(remark.split())
                
                if not remark.strip():
                    st.error("Please type a remark before submitting.")
                elif word_count > 400:
                    # Strict word count enforcement
                    st.error(f"⚠️ Your remark is {word_count} words long. Please shorten it to a maximum of 400 words.")
                else:
                    today_date = datetime.date.today().strftime("%Y-%m-%d") 
                    
                    cursor = conn.cursor()
                    cursor.execute('SELECT MAX(remark_id) FROM "Lecturer_Remarks"')
                    max_id_result = cursor.fetchone()[0]
                    new_remark_id = 1 if max_id_result is None else int(max_id_result) + 1
                    
                    # FIXED: Postgres SQL syntax
                    cursor.execute("""
                        INSERT INTO "Lecturer_Remarks" (remark_id, user_id, remark_text, status, submit_date) 
                        VALUES (%s, %s, %s, 'Unread', %s)
                    """, (new_remark_id, st.session_state.user_id, remark, today_date))
                    
                    conn.commit()
                    st.success("Your remark has been successfully flagged for the Registry Office!")
                    
        st.divider()

        # --- SECTION: GENERAL DOCUMENT VAULT ---
        st.subheader("📁 Personal Document Vault")
        st.write("Securely upload versatile PDF documents (e.g., medical certificates, standard forms) to your profile. No special conditions are required.")
        
        with st.form("general_doc_upload_form", clear_on_submit=True):
            doc_title = st.text_input("Document Title / Description", placeholder="e.g., Medical Certificate - Nov 2026")
            general_pdf = st.file_uploader("Upload File (PDF only)", type=["pdf"])
            
            if st.form_submit_button("Upload to Vault"):
                if not doc_title.strip():
                    st.error("⚠️ Please provide a title or description for your document.")
                elif general_pdf is None:
                    st.error("⚠️ Please select a PDF file to upload.")
                else:
                    try:
                        doc_bytes = general_pdf.read()
                        upload_date = datetime.date.today().strftime("%Y-%m-%d")
                        
                        cursor = conn.cursor()
                        # Auto-create the table if it doesn't exist to prevent crashes
                        cursor.execute('''
                            CREATE TABLE IF NOT EXISTS "Lecturer_Documents" (
                                doc_id SERIAL PRIMARY KEY,
                                user_id INTEGER,
                                document_title TEXT,
                                document_file BYTEA,
                                upload_date DATE
                            )
                        ''')
                        
                        cursor.execute('''
                            INSERT INTO "Lecturer_Documents" (user_id, document_title, document_file, upload_date)
                            VALUES (%s, %s, %s, %s)
                        ''', (st.session_state.user_id, doc_title, doc_bytes, upload_date))
                        
                        conn.commit()
                        st.success(f"✅ '{doc_title}' successfully uploaded to your vault!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Database Error: {e}")
        
        # Display uploaded documents
        try:
            cursor.execute('SELECT doc_id, document_title, upload_date, document_file FROM "Lecturer_Documents" WHERE user_id = %s ORDER BY doc_id DESC', (st.session_state.user_id,))
            saved_docs = cursor.fetchall()
            
            if saved_docs:
                with st.expander("📂 View My Uploaded Documents", expanded=True):
                    for doc in saved_docs:
                        d_id, d_title, d_date, d_bytes = doc
                        col_doc, col_btn = st.columns([3, 1])
                        with col_doc:
                            st.markdown(f"**{d_title}** *(Uploaded: {d_date})*")
                        with col_btn:
                            st.download_button(
                                label="📥 Download",
                                data=d_bytes,
                                file_name=f"{d_title.replace(' ', '_')}.pdf",
                                mime="application/pdf",
                                key=f"dl_gen_doc_{d_id}"
                            )
                        st.divider()
        except Exception:
            # THE FIX: PostgreSQL requires a rollback after a failed query before you can run the next one!
            conn.rollback()
            pass
            
        st.divider()

        # --- SECTION: ENTERPRISE WORKLOAD & HISTORICAL LOG ---
        st.subheader("📚 My Teaching Workload")
        
        # --- THE FIX: Injected 'm.department' into the SQL Query! ---
        my_modules_query = """
            SELECT a.semester as "Semester", 
                   a.module_code as "Module Code", 
                   m.module_name as "Module Title", 
                   m.department as "Department",
                   m.programme as "Programme",
                   a.level_semester as "Cohort", 
                   u.employment_type as "FT/PT",
                   m.lecture_hours as "L. Hrs",
                   a.students_count as "Students", 
                   m.weightage as "Weightage",
                   m.programme_coordinator as "Coordinator"
            FROM "Allocations" a
            JOIN "Modules" m ON a.module_code = m.module_code
            JOIN "Users" u ON a.user_id = u.user_id
            WHERE a.user_id = %s
            ORDER BY a.semester DESC
        """
        my_modules_df = pd.read_sql_query(my_modules_query, conn, params=(st.session_state.user_id,))
        
        if my_modules_df.empty:
            st.info("You currently have no modules assigned to you for any semester.")
            workload_count = 0  # Fallback for the promotion logic
        else:
            # Let the Lecturer toggle which semester is "Active" right now
            col_sem, _ = st.columns([1, 2])
            with col_sem:
                active_semester = st.selectbox("Select Active Semester:", ["Semester 1", "Semester 2"])
            
            # Split the data based on their selection
            active_df = my_modules_df[my_modules_df['Semester'] == active_semester]
            past_df = my_modules_df[my_modules_df['Semester'] != active_semester]
            
            # 1. THE ACTIVE WORKLOAD
            st.markdown(f"**Current Workload ({active_semester})**")
            if not active_df.empty:
                st.dataframe(active_df.drop(columns=['Semester']), use_container_width=True, hide_index=True)
                
                # Calculate live metrics
                workload_count = len(active_df)  # This feeds into your promotion logic!
                total_students = active_df['Students'].sum()
                total_weight = active_df['Weightage'].sum()
                
                st.caption(f"📊 **{active_semester} Totals:** {workload_count} Modules | {total_students} Students | {total_weight} Total Weightage")
            else:
                st.info(f"No modules assigned for {active_semester}.")
                workload_count = 0
                
            # 2. THE SUPERVISOR'S HISTORICAL LOG
            if not past_df.empty:
                with st.expander("📂 View Previous Semester Historical Log"):
                    st.info("This is a permanent record of your past teaching allocations.")
                    st.dataframe(past_df.drop(columns=['Semester']), use_container_width=True, hide_index=True)
            
            # --- PDF & EXCEL EXPORTS ---
            st.write("### 🖨️ Export Official Workload Report")
            st.info("Download a formatted PDF summary of your entire workload across all semesters for board meetings and records.")
            
            # THE FIX: Split the execute and fetchone to avoid the AttributeError
            cursor.execute('SELECT name, role FROM "Users" WHERE user_id = %s', (st.session_state.user_id,))
            user_data = cursor.fetchone()
            
            lec_name = user_data[0]
            lec_role = user_data[1]
            
            def create_workload_pdf(name, role, df):
                pdf = FPDF()
                pdf.add_page()
                
                # Header
                pdf.set_font("Arial", "B", 16)
                pdf.cell(0, 10, "UNIVERSITY OF TECHNOLOGY, MAURITIUS", ln=True, align="C")
                pdf.set_font("Arial", "I", 12)
                pdf.cell(0, 10, "Official Lecturer Workload Summary", ln=True, align="C")
                pdf.ln(10)
                
                # Lecturer Info
                pdf.set_font("Arial", "", 12)
                date_str = datetime.datetime.now().strftime("%d %B %Y")
                pdf.cell(0, 8, f"Date of Report: {date_str}", ln=True)
                pdf.cell(0, 8, f"Lecturer Name: {name}", ln=True)
                pdf.cell(0, 8, f"Designation: {role}", ln=True)
                pdf.ln(5)
                
                # Summary Statistics
                total_students = df['Students'].sum()
                total_modules = len(df)
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, f"Total Assigned Modules: {total_modules}  |  Total Students: {total_students}", ln=True)
                pdf.ln(5)
                
                # --- THE FIX: Squeezed 'Dept' into the PDF Table ---
                pdf.set_font("Arial", "B", 10)
                pdf.set_fill_color(200, 200, 200) 
                pdf.cell(20, 10, "Sem", border=1, fill=True)
                pdf.cell(20, 10, "Code", border=1, fill=True)
                pdf.cell(20, 10, "Dept", border=1, fill=True)
                pdf.cell(70, 10, "Module Title", border=1, fill=True)
                pdf.cell(30, 10, "Cohort", border=1, fill=True)
                pdf.cell(30, 10, "Students", border=1, fill=True, ln=True)
                
                # Table Body
                pdf.set_font("Arial", "", 9)
                for index, row in df.iterrows():
                    sem_str = str(row['Semester']).replace('Semester ', 'S') # Abbreviate to fit width
                    pdf.cell(20, 10, sem_str, border=1)
                    pdf.cell(20, 10, str(row['Module Code']), border=1)
                    
                    # Prevent long department names from breaking the table
                    dept_str = str(row.get('Department', 'Unassigned'))
                    if len(dept_str) > 8: dept_str = dept_str[:6] + ".."
                    pdf.cell(20, 10, dept_str, border=1)
                    
                    # Prevent long module titles from breaking the table
                    title = str(row['Module Title'])
                    if len(title) > 35: title = title[:32] + "..."
                    pdf.cell(70, 10, title, border=1)
                    
                    pdf.cell(30, 10, str(row['Cohort']), border=1)
                    pdf.cell(30, 10, str(row['Students']), border=1, ln=True)
                    
                pdf.ln(15)
                pdf.set_font("Arial", "I", 9)
                pdf.cell(0, 10, "This is an officially generated workload report from the University Registry System.", ln=True, align="C")
                
                try:
                    return pdf.output(dest='S').encode('latin-1')
                except:
                    return bytes(pdf.output())

            # Generate the PDF in the background
            pdf_bytes = create_workload_pdf(lec_name, lec_role, my_modules_df)
            
            # The magical PDF Download Button
            st.download_button(
                label="📥 Download Official Workload PDF",
                data=pdf_bytes,
                file_name=f"Workload_Summary_{lec_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary"
            )
            
            # --- NEW: EXCEL EXPORT ---
            excel_buffer = io.BytesIO()
            # We use openpyxl to write the dataframe straight to an Excel format
            my_modules_df.to_excel(excel_buffer, index=False, engine='openpyxl')
            excel_data = excel_buffer.getvalue()
            
            st.download_button(
                label="📊 Download Workload as Excel",
                data=excel_data,
                file_name=f"Workload_Data_{lec_name.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        st.divider()

        conn.close()
        
   # --- TABBED HOD VIEW ---
    def hod_dashboard():
        st.title("🎓 Head of Department Dashboard")
        st.write("Oversee departmental module allocations and review staff promotion requests.")
        
        # --- GLOBAL DEPARTMENT FILTER ---
        conn = cloud_engine.raw_connection()
        # Fetch available departments dynamically to populate the dropdown
        dept_df = pd.read_sql_query('SELECT DISTINCT department FROM "Users" WHERE department IS NOT NULL AND department != \'Unassigned\'', conn)
        hod_dept_list = ["All Departments"] + sorted([d for d in dept_df['department'].tolist() if d])
        
        st.markdown("### 🏢 Department Focus")
        selected_hod_dept = st.selectbox("Select Department to Monitor:", hod_dept_list)
        st.divider()
        
        # Generate the SQL injection string for filtering
        dept_sql_filter = ""
        dept_params = []
        if selected_hod_dept != "All Departments":
            # We use 'u.department' because almost all queries below join the Users table as 'u'
            dept_sql_filter = " AND u.department = %s "
            dept_params.append(selected_hod_dept)
            
        # Make sure your tab variables match this list!
        tab1, tab2, tab3 = st.tabs(["Overview", "Promotion Approvals", "Department Analytics"])
        
        # --- TAB 1: ALLOCATIONS OVERVIEW & METRICS ---
        with tab1:
            st.subheader(f"Department Workload & Metrics ({selected_hod_dept})")
            try:
                # --- NEW: SYSTEM ALERTS (QUOTAS & PROMOTIONS) ---
                # Added u.department and injected the dept_sql_filter
                alert_query = f"""
                    SELECT u.name as "Staff Member", u.department as "Department", u.role as "Role", u.research_status as "Research_Status", COUNT(a.module_code) as "Assigned Modules"
                    FROM "Users" u
                    LEFT JOIN "Allocations" a ON u.user_id = a.user_id
                    WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')
                    {dept_sql_filter}
                    GROUP BY u.user_id, u.name, u.department, u.role, u.research_status
                """
                alert_df = pd.read_sql_query(alert_query, conn, params=tuple(dept_params))
                
                # Create an empty list to store ONLY the people who exceed limits
                flagged_data = []
                
                for index, row in alert_df.iterrows():
                    role = row['Role']
                    research = str(row['Research_Status']).strip() if pd.notna(row['Research_Status']) else "Unsatisfactory"
                    assigned = int(row['Assigned Modules'])
                    dept_name = row['Department']
                    
                    # Define dynamic limits exactly like the Registry constraints (Annex Math)
                    normal, excess_sat, excess_unsat = 0, 0, 0
                    if role == "HoS": normal, excess_sat, excess_unsat = 2, 4, 2
                    elif role == "HoD": normal, excess_sat, excess_unsat = 4, 4, 2
                    elif role in ["Professor", "Associate Professor"]: normal, excess_sat, excess_unsat = 5, 4, 2
                    elif role == "Senior Lecturer": normal, excess_sat, excess_unsat = 5, 2, 1
                    elif role == "Lecturer": normal, excess_sat, excess_unsat = 6, 6, 3
                
                    allowed_excess = excess_sat if research == "Satisfactory" else excess_unsat
                    max_allowed = normal + allowed_excess
                    
                    # THE FIX: Added both Normal Quantum AND Max Allowed to both dictionaries
                    # so Pandas doesn't convert the columns to decimals (floats) to handle missing values!
                    if assigned > max_allowed:
                        flagged_data.append({
                            "Staff Member": row['Staff Member'],
                            "Department": dept_name,
                            "Role": role,
                            "Assigned": assigned,
                            "Normal Quantum": normal,
                            "Max Allowed": max_allowed,
                            "Alert Type": "🚨 OVERLOAD"
                        })
                    elif assigned > normal:
                        flagged_data.append({
                            "Staff Member": row['Staff Member'],
                            "Department": dept_name,
                            "Role": role,
                            "Assigned": assigned,
                            "Normal Quantum": normal,
                            "Max Allowed": max_allowed,
                            "Alert Type": "⚠️ EXCESS"
                        })
                
                # If the list has people in it, draw the clean Alert Table
                if flagged_data:
                    st.write("### 🚨 Staff Quota Alerts")
                    flag_df = pd.DataFrame(flagged_data)
                    
                    # Add background colors based on the alert type
                    def highlight_alerts(row):
                        if row['Alert Type'] == '🚨 OVERLOAD':
                            return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
                        elif row['Alert Type'] == '⚠️ EXCESS':
                            return ['background-color: rgba(255, 215, 0, 0.2)'] * len(row)
                        return [''] * len(row)
                    
                    styled_flag_df = flag_df.style.apply(highlight_alerts, axis=1)
                    st.dataframe(styled_flag_df, use_container_width=True, hide_index=True)
                else:
                    st.info("✅ All staff workloads are within normal limits. No pending alerts.")
                
                st.divider()

                # --- 1. GLOBAL SEMESTER FILTER ---
                selected_semester = st.radio("⏳ Select Semester to Analyze:", ["Semester 1", "Semester 2"], horizontal=True, key="hod_sem")
                st.divider()

                # --- 2. ENTERPRISE METRICS ---
                cursor = conn.cursor()
                # Injecting department filter into metrics
                staff_query = f'SELECT COUNT(*) FROM "Users" u WHERE u.role IN (\'Lecturer\', \'Senior Lecturer\', \'Associate Professor\', \'Professor\') {dept_sql_filter}'
                cursor.execute(staff_query, tuple(dept_params))
                staff_count = cursor.fetchone()[0]
                
                # Requires joining Users to filter by department
                sem_query = f"""
                    SELECT COUNT(a.module_code), SUM(a.students_count), SUM(m.weightage)
                    FROM "Allocations" a
                    JOIN "Modules" m ON a.module_code = m.module_code
                    JOIN "Users" u ON a.user_id = u.user_id
                    WHERE a.semester = %s {dept_sql_filter}
                """
                sem_params = [selected_semester] + dept_params
                cursor.execute(sem_query, tuple(sem_params))
                sem_stats = cursor.fetchone()
                
                mod_count = sem_stats[0] if sem_stats and sem_stats[0] else 0
                student_count = sem_stats[1] if sem_stats and sem_stats[1] else 0
                total_weight = sem_stats[2] if sem_stats and sem_stats[2] else 0
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Teaching Staff", staff_count)
                m2.metric("Assigned Modules", mod_count)
                m3.metric("Total Students", student_count)
                m4.metric("Total Weightage", total_weight)
                
                st.divider()

                # --- 3. YOUR DUAL-FILTER SYSTEM (RESTORED & UPGRADED) ---
                st.write(f"### Detailed Allocations ({selected_semester})")
                
                # Added u.department and the dept_sql_filter
                alloc_query = f"""
                    SELECT u.name as "Lecturer", u.title as "Title", u.department as "Department",
                           a.module_code as "Module Code", m.module_name as "Module Title", 
                           a.level_semester as "Cohort", a.students_count as "Students", m.weightage as "Weightage"
                    FROM "Allocations" a
                    JOIN "Users" u ON a.user_id = u.user_id
                    JOIN "Modules" m ON a.module_code = m.module_code
                    WHERE a.semester = %s {dept_sql_filter}
                """
                alloc_df = pd.read_sql_query(alloc_query, conn, params=tuple([selected_semester] + dept_params))
                
                col1, col2 = st.columns(2)
                
                with col1:
                    lecturer_list = ["All Lecturers"] + sorted(alloc_df["Lecturer"].unique().tolist()) if not alloc_df.empty else ["All Lecturers"]
                    selected_lecturer = st.selectbox("👤 Filter by Lecturer", lecturer_list)
                    
                with col2:
                    module_list = ["All Modules"] + sorted(alloc_df["Module Code"].unique().tolist()) if not alloc_df.empty else ["All Modules"]
                    selected_module = st.selectbox("📚 Filter by Module Code", module_list)
                
                display_df = alloc_df
                
                if selected_lecturer != "All Lecturers":
                    display_df = display_df[display_df["Lecturer"] == selected_lecturer]
                    
                if selected_module != "All Modules":
                    display_df = display_df[display_df["Module Code"] == selected_module]
                    
                met_col1, met_col2, met_col3 = st.columns(3)
                with met_col1:
                    st.metric(label="Showing Modules", value=len(display_df))
                with met_col2:
                    st.metric(label="Unique Lecturers", value=display_df["Lecturer"].nunique())
                with met_col3:
                    st.metric(label="Filtered Students", value=int(display_df["Students"].sum()) if not display_df.empty else 0)
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Error loading allocations: {e}")

        # --- TAB 2: PROMOTION APPROVALS ---
        with tab2:
            st.subheader("Promotion Requests (Action Required)")
            try:
                # Added u.department and the dept_sql_filter
                promo_query = f"""
                    SELECT p.ticket_id, u.name as "Applicant", u.department as "Department", u.role as "Current Role", 
                        p.proposed_role as "Requested Role", p.status
                    FROM "Pending_Promotions" p
                    JOIN "Users" u ON p.user_id = u.user_id
                    WHERE p.status = 'Pending HoD' {dept_sql_filter}
                """
                promo_df = pd.read_sql_query(promo_query, conn, params=tuple(dept_params))
                
                if promo_df.empty:
                    st.info("✅ No pending promotions require your approval at this time.")
                else:
                    st.dataframe(promo_df, use_container_width=True, hide_index=True)
                    st.divider()

                    # --- REVIEW APPLICATION LETTER SECTION ---
                    st.write("### 📄 Review Application Letter")
                    view_ticket = st.selectbox("Select Ticket ID to Download Letter:", promo_df['ticket_id'], key="hod_letter_select")
                    
                    cursor = conn.cursor()
                    cursor.execute('SELECT u.name, p.registration_letter FROM "Pending_Promotions" p JOIN "Users" u ON p.user_id = u.user_id WHERE p.ticket_id = %s', (int(view_ticket),))
                    letter_data = cursor.fetchone()
                    
                    if letter_data and letter_data[1]:
                        applicant_name = letter_data[0]
                        pdf_bytes = letter_data[1]
                        
                        st.download_button(
                            label=f"📥 Download Registration Letter ({applicant_name})",
                            data=pdf_bytes,
                            file_name=f"Registration_Letter_{applicant_name.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            type="secondary"
                        )
                    else:
                        st.warning("⚠️ No registration letter is attached to this ticket.")
                        
                    st.divider()

                    st.write("### Process a Request")
                    with st.form("hod_promo_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            selected_ticket = st.selectbox("Select Ticket ID", promo_df['ticket_id'])
                        with col2:
                            action = st.radio("Decision", ["Approve (Forward to HoS)", "Reject"], horizontal=True)
                            
                        rejection_reason = st.text_area("Rejection Reason (Required if Rejecting)")
                        
                        if st.form_submit_button("Submit Decision", use_container_width=True):
                            if "Reject" in action and not rejection_reason.strip():
                                st.error("You must provide a rejection reason for the applicant.")
                            else:
                                cursor = conn.cursor()
                                new_status = 'Pending HoS' if 'Approve' in action else 'Rejected'
                                
                                cursor.execute('UPDATE "Pending_Promotions" SET status = %s, rejection_reason = %s WHERE ticket_id = %s', (new_status, rejection_reason, selected_ticket))
                                conn.commit()
                                st.success(f"Ticket #{selected_ticket} has been marked as: {new_status}")
                                st.rerun()
            except Exception as e:
                st.error(f"Error loading promotions: {e}")

        # --- TAB 3: DEPARTMENT ANALYTICS ---
        with tab3:
            st.subheader("📈 Department Workload & Analytics")
            try:
                col1, col2 = st.columns(2)
                
                # Injected dept_sql_filter
                total_staff_query = f"SELECT COUNT(*) FROM \"Users\" u WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor') {dept_sql_filter}"
                total_staff = pd.read_sql_query(total_staff_query, conn, params=tuple(dept_params)).iloc[0,0]
                
                # Joined users table to inject dept_sql_filter
                pending_hod_query = f"""
                    SELECT COUNT(*) FROM "Pending_Promotions" p 
                    JOIN "Users" u ON p.user_id = u.user_id 
                    WHERE p.status = 'Pending HoD' {dept_sql_filter}
                """
                pending_hod = pd.read_sql_query(pending_hod_query, conn, params=tuple(dept_params)).iloc[0,0]
                
                col1.metric("Total Teaching Staff", total_staff)
                col2.metric("Pending HoD Reviews", pending_hod)
                
                st.divider()
                
                st.write("### 📊 Annual Workload Comparison")
                st.info("Displays the total module workload for each teaching staff member, split by semester.")
                
                # Injected dept_sql_filter
                chart_query = f"""
                    SELECT u.name as "Staff Member", a.semester, COUNT(a.module_code) as "Module Count"
                    FROM "Users" u
                    JOIN "Allocations" a ON u.user_id = a.user_id
                    WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor')
                    {dept_sql_filter}
                    GROUP BY u.name, a.semester
                """
                chart_df = pd.read_sql_query(chart_query, conn, params=tuple(dept_params))
                
                if not chart_df.empty:
                    chart_data = chart_df.pivot(index='Staff Member', columns='semester', values='Module Count').fillna(0)
                    st.line_chart(chart_data, use_container_width=True)
                else:
                    st.info("No workload data available to chart.")
                    
            except Exception as e:
                st.error(f"Error loading analytics: {e}")
                
        # Move conn.close() outside the tabs so it executes once at the end
        conn.close()

    # --- TABBED HOS VIEW ---
    def hos_dashboard():
        st.title("🏛️ Head of School Dashboard")
        st.write("Finalize staff promotions and oversee school-wide metrics.")
        
        tab1, tab2 = st.tabs(["Final Promotion Approvals", "School Overview"])
        
        # --- TAB 1: EXECUTIVE OVERVIEW & PROMOTIONS ---
        with tab1:
            st.subheader("School Executive Overview")
            conn = cloud_engine.raw_connection()
            try:
                # ==========================================
                # SECTION A: THE NEW ENTERPRISE METRICS
                # ==========================================
                selected_semester = st.radio("⏳ Select Semester to Analyze:", ["Semester 1", "Semester 2"], horizontal=True, key="hos_sem")
                st.divider()
                
                # School-Wide Metrics
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(DISTINCT department) FROM "Users" WHERE department != \'Unassigned\' AND department IS NOT NULL')
                dept_count = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT COUNT(DISTINCT programme) FROM "Modules" WHERE programme != \'General\' AND programme IS NOT NULL')
                prog_count = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT COUNT(a.module_code), SUM(a.students_count) FROM "Allocations" a WHERE a.semester = %s', (selected_semester,))
                school_stats = cursor.fetchone()
                
                total_classes = school_stats[0] if school_stats and school_stats[0] else 0
                total_students = school_stats[1] if school_stats and school_stats[1] else 0
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Active Departments", dept_count)
                col2.metric("Active Programmes", prog_count)
                col3.metric("Running Classes", total_classes)
                col4.metric("Student Enrollments", int(total_students) if total_students else 0)
                
                st.divider()
                
                # RESTORED: Department Performance Table
                st.write(f"### Department Performance ({selected_semester})")
                dept_df = pd.read_sql_query("""
                    SELECT 
                        u.department as "Department",
                        COUNT(DISTINCT u.user_id) as "Staff Count",
                        COUNT(a.module_code) as "Modules Taught",
                        SUM(a.students_count) as "Total Students",
                        SUM(m.weightage) as "Total Weightage"
                    FROM "Users" u
                    LEFT JOIN "Allocations" a ON u.user_id = a.user_id AND a.semester = %s
                    LEFT JOIN "Modules" m ON a.module_code = m.module_code
                    WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD')
                    AND u.department != 'Unassigned'
                    GROUP BY u.department
                    ORDER BY "Total Students" DESC
                """, conn, params=(selected_semester,))
                
                dept_df.fillna(0, inplace=True)
                st.dataframe(dept_df, use_container_width=True, hide_index=True)
                
                st.divider()

                # ==========================================
                # SECTION B: YOUR FINAL PROMOTION APPROVALS
                # ==========================================
                st.subheader("Pending Final Approvals")
                
                # FIXED: Removed proposed_category to match the new Role-only architecture
                promo_df = pd.read_sql_query("""
                    SELECT p.ticket_id, u.name as "Applicant", u.role as "Current Role", 
                        p.proposed_role as "Requested Role"
                    FROM "Pending_Promotions" p
                    JOIN "Users" u ON p.user_id = u.user_id
                    WHERE p.status = 'Pending HoS'
                """, conn)
                
                if promo_df.empty:
                    st.info("✅ No promotions require final approval at this time.")
                else:
                    st.dataframe(promo_df, use_container_width=True, hide_index=True)
                    
                    st.divider()

                    # --- REVIEW APPLICATION LETTER SECTION ---
                    st.write("### 📄 Review Application Letter")
                    view_ticket = st.selectbox("Select Ticket ID to Download Letter:", promo_df['ticket_id'], key="hos_letter_select")
                    
                    # Fetch the PDF BLOB from the database
                    cursor = conn.cursor()
                    cursor.execute('SELECT u.name, p.registration_letter FROM "Pending_Promotions" p JOIN "Users" u ON p.user_id = u.user_id WHERE p.ticket_id = %s', (int(view_ticket),))
                    letter_data = cursor.fetchone()
                    
                    if letter_data and letter_data[1]:
                        applicant_name = letter_data[0]
                        pdf_bytes = letter_data[1]
                        
                        st.download_button(
                            label=f"📥 Download Registration Letter ({applicant_name})",
                            data=pdf_bytes,
                            file_name=f"Registration_Letter_{applicant_name.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            type="secondary"
                        )
                    else:
                        st.warning("⚠️ No registration letter is attached to this ticket. (Legacy Application)")
                        
                    st.divider()

                    st.write("### Finalize Request")
                    
                    with st.form("hos_promo_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            selected_ticket = st.selectbox("Select Ticket ID", promo_df['ticket_id'])
                        with col2:
                            action = st.radio("Final Decision", ["Approve & Apply Promotion", "Reject"], horizontal=True)
                            
                        rejection_reason = st.text_area("Rejection Reason (Required if Rejecting)")
                            
                        if st.form_submit_button("Submit Final Decision", use_container_width=True):
                            if "Reject" in action and not rejection_reason.strip():
                                st.error("You must provide a rejection reason for the applicant.")
                            else:
                                cursor = conn.cursor()
                                
                                if "Approve" in action:
                                    # RESTORED: Auto-updating the user's role in the Users table upon approval!
                                    cursor.execute('SELECT user_id, proposed_role FROM "Pending_Promotions" WHERE ticket_id = %s', (selected_ticket,))
                                    ticket_data = cursor.fetchone()
                                    target_user_id = ticket_data[0]
                                    new_role = ticket_data[1]
                                    
                                    # Update the actual user profile
                                    cursor.execute('UPDATE "Users" SET role = %s WHERE user_id = %s', (new_role, target_user_id))
                                    # Update the ticket status
                                    cursor.execute('UPDATE "Pending_Promotions" SET status = \'Approved\', rejection_reason = \'\' WHERE ticket_id = %s', (selected_ticket,))
                                    st.success(f"Promotion Approved! The applicant's official role has been updated to {new_role}.")
                                else:
                                    cursor.execute('UPDATE "Pending_Promotions" SET status = \'Rejected\', rejection_reason = %s WHERE ticket_id = %s', (rejection_reason, selected_ticket))
                                    st.warning(f"Ticket #{selected_ticket} has been Rejected.")
                                    
                                conn.commit()
                                st.rerun()
                
            except Exception as e:
                st.error(f"Error loading dashboard: {e}")
            conn.close()

        # --- TAB 2: SCHOOL OVERVIEW (VISUAL ANALYTICS) ---
        with tab2:
            st.subheader("📊 School Analytics & Demographics")
            conn = cloud_engine.raw_connection()
            
            try:
                # 1. High-Level Metrics (Top Row)
                col1, col2, col3 = st.columns(3)
                
                # Fetching live counts from the database
                total_staff = pd.read_sql_query("SELECT COUNT(*) FROM \"Users\" WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')", conn).iloc[0,0]
                total_modules = pd.read_sql_query('SELECT COUNT(*) FROM "Modules"', conn).iloc[0,0]
                pending_promos = pd.read_sql_query("SELECT COUNT(*) FROM \"Pending_Promotions\" WHERE status = 'Pending HoS'", conn).iloc[0,0]
                
                col1.metric("Total Academic Staff", total_staff)
                col2.metric("Total Active Modules", total_modules)
                col3.metric("Pending Final Approvals", pending_promos)
                
                st.divider()
                
                # 2. Visual Charts (Middle Row)
                st.write("### Staff Distribution by Role")
                
                # Query to group staff by role
                role_df = pd.read_sql_query("""
                    SELECT role, COUNT(user_id) as Count 
                    FROM "Users" 
                    WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS') 
                    GROUP BY role
                """, conn)
                
                # Setting the index allows Streamlit to automatically label the X-axis
                if not role_df.empty:
                    role_df.set_index('role', inplace=True)
                    st.bar_chart(role_df)
                else:
                    st.info("No staff data available to chart.")
                
                st.divider()
                
                # 3. Detailed Breakdown Table (Bottom Row)
                st.write("### Department Workload Breakdown")
                workload_df = pd.read_sql_query("""
                    SELECT u.name as "Staff Name", u.role as "Role", COUNT(a.module_code) as "Assigned Modules"
                    FROM "Users" u
                    LEFT JOIN "Allocations" a ON u.user_id = a.user_id
                    WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')
                    GROUP BY u.user_id, u.name, u.role
                    ORDER BY "Assigned Modules" DESC
                """, conn)
                
                st.dataframe(workload_df, use_container_width=True, hide_index=True)
                
            except Exception as e:
                st.error(f"Error loading analytics: {e}")
                
            conn.close()

    # ==========================================
    #       THE TRAFFIC COP (ROLE-BASED ROUTING)
    # ==========================================

    # 1. Diagnostic Line (Helps us see if there's a typo in the role name)
    if 'user_role' in st.session_state:
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

