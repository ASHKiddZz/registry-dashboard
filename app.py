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
        
        # This section checks if there are any unread remarks, if so it is flagged with a message.
        conn = sqlite3.connect('registry_database.db')
        
        try:
            remarks_df = pd.read_sql_query("""
                SELECT r.remark_id, u.name as "Lecturer Name", r.remark_text as "Remark", r.submit_date as "Date"
                FROM Lecturer_Remarks r
                JOIN "Users" u ON r.user_id = u.user_id
                WHERE r.status = 'Unread'
            """, conn)

            if not remarks_df.empty:
                # The st.expander creates a sort of drop down box that is bright and noticeable.
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
        except Exception as e:
            # If the database crashes here, we will now see exactly why it did.
            st.error(f"Error loading remarks: {e}")
            
        conn.close()
    
        st.divider()
        
        # Building the tabs within the registry dashboard.
        tab1, tab2, tab3, tab4 = st.tabs(["Manage Users", "Manage Modules", "Allocations Overview", "Promotions & Rotations"])
        
        with tab1:
            st.subheader("Current System Users")
            
            # --- 1. FIXED: Connect to Cloud Database instead of local SQLite ---
            conn = cloud_engine.raw_connection()
            
            # FIXED: Added quotes around "Users" for Postgres case-sensitivity
            users_df = pd.read_sql_query('SELECT user_id, name, role, category_level FROM "Users"', conn)
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # This section allows the Admin to edit and delete Users within the database.
            st.subheader("Edit or Delete Staff")
            
            # 1. First check if the database is completely empty
            if users_df.empty:
                st.info("No staff members found. Please use the Bulk Import tab to add staff!")
                st.stop() 

            # --- 2. FIXED INDENTATION: Pulled back out of the 'if' statement ---
            # This creates a drop down user list also listing the names of the users with their id.
            user_list = users_df['user_id'].astype(str) + " - " + users_df['name']
            selected_user_str = st.selectbox("Select User to Modify", user_list)

            # 3. Get the ID (No 'if' needed here anymore)
            selected_id = int(selected_user_str.split(" - ")[0])
            
            # Grab that specific user's current data to fill the default values
            current_data = users_df[users_df['user_id'] == selected_id].iloc[0]
            
            col1, col2 = st.columns(2)
            with col1:
                # The Users' name is what they will use to login as their username.
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
                
                # This is a feature that allows a password reset incase they forget their password.
                edit_password = st.text_input("Reset Password (leave blank to keep current)", type="password")
                
            st.write("Actions:")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("Update User", use_container_width=True):
                    cursor = conn.cursor()
                    # --- 3. FIXED: Changed ? to %s and wrapped table in quotes ---
                    if edit_password: 
                        cursor.execute('UPDATE "Users" SET name=%s, role=%s, category_level=%s, password=%s WHERE user_id=%s', 
                                       (edit_name, edit_role, edit_level, edit_password, selected_id))
                    else: 
                        cursor.execute('UPDATE "Users" SET name=%s, role=%s, category_level=%s WHERE user_id=%s', 
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
                        cursor.execute('DELETE FROM "Users" WHERE user_id=%s', (selected_id,))
                        cursor.execute('DELETE FROM "Allocations" WHERE user_id=%s', (selected_id,))
                        conn.commit()
                        st.warning(f"User deleted from system!")
                        st.rerun()

            st.divider()
            
            # This section is to be able to manually add a new user providing all necessary informations within each field box.
            st.subheader("Register New Staff Member")
            with st.form("add_user_form", clear_on_submit=True):
                new_name = st.text_input("Full Name")
                new_role = st.selectbox("Role", ["Lecturer", "Senior Lecturer", "Associate Professor", "Professor", "HoD", "HoS", "Registry Officer"])
                new_level = st.selectbox("Category Limit", ["Category 1 (HoS)", "Category 2 (HoD)", "Category 3 (TBD)", "Category 4 (PhD Staff)", "Category 5 (Other Academic)", "N/A"])
    
                # This section is to manually insert the hire year of a specific user.
                current_yr = datetime.datetime.now().year
                new_hire_year = st.number_input("Year Hired", min_value=1990, max_value=current_yr, value=current_yr)
    
                new_pass = st.text_input("Temporary Password", type="password")

                submit_user = st.form_submit_button("Create Account")

                if submit_user:
                    if new_name and new_pass:
                        cursor = conn.cursor()
                        cursor.execute('INSERT INTO "Users" (name, role, category_level, password, hire_year) VALUES (%s, %s, %s, %s, %s)', 
                                       (new_name, new_role, new_level, new_pass, new_hire_year))
                        conn.commit()
                        st.success(f"Account created for {new_name}!")
                        st.rerun()
                    else:
                        st.error("Please fill out the Name and Password fields.")
            
            # This creates a fine line between each section to make it appear more clean.
            st.divider()
            st.subheader("📥 Bulk Import Staff (Annex Upload)")

            # This is the rectangular box where you can drag and drop files that needs to be imported on the database.
            uploaded_file = st.file_uploader("Upload staff list (CSV or Excel)", type=['csv', 'xlsx'])

            if uploaded_file is not None:
                # It will read the file into Pandas.
                try:
                    if uploaded_file.name.endswith('.csv'):
                        import_df = pd.read_csv(uploaded_file)
                    else:
                        import_df = pd.read_excel(uploaded_file)
                    # When the excel document is uploaded, a small preview wil be displayed with the first 3 rows showing on the overview table.
                    st.write("Preview of uploaded document:")
                    st.dataframe(import_df.head(3))

                    # This is the import button feature to register all data on the imported document to the database.
                    if st.button("Process & Import Users"):
                        cursor = conn.cursor()
                        added_count = 0
                        skipped_count = 0

                        for index, row in import_df.iterrows():
                            staff_name = str(row.get('Name', '')).strip()
                            staff_role = str(row.get('Role', '')).strip()
                            category = str(row.get('Category_Level', 'N/A')).strip()

                            if staff_name and staff_name != 'nan':

                                # Check if this person is already in the database.
                                cursor.execute('SELECT * FROM "Users" WHERE name=%s', (staff_name,))
                                if not cursor.fetchone():
                                    # This is creates the account of the user with a default password which they can later change once they login on their dashboard.
                                    cursor.execute('INSERT INTO "Users" (name, role, category_level, password) VALUES (%s, %s, %s, %s)',
                                                   (staff_name, staff_role, category, 'welcome123'))
                                    added_count += 1
                                else:
                                    skipped_count += 1 # This skips the whole code if the user already exists within the database.

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
            conn = sqlite3.connect('registry_database.db')
            modules_df = pd.read_sql_query("SELECT * FROM Modules", conn)
            
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
            
            # This is the section where to admin can manually add or edit modules.
            st.subheader("Edit or Delete Module")
            
            if not modules_df.empty:
                module_list = modules_df['module_code'].astype(str) + " - " + modules_df['module_name']
                selected_mod_str = st.selectbox("Select Module to Modify", module_list)
                
                if selected_mod_str:
                    selected_mod_id = selected_mod_str.split(" - ")[0]
                    current_mod_data = modules_df[modules_df['module_code'] == selected_mod_id].iloc[0]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"Editing Module Code: **{selected_mod_id}**")
                        edit_m_name = st.text_input("Update Module Name", value=current_mod_data['module_name'])
                        
                        # .get() safely pulls the number, or defaults to the second number if missing.
                        default_dur = int(current_mod_data.get('duration', 12))
                        edit_duration = st.number_input("Update Duration (Weeks)", min_value=1, value=default_dur)
                        
                    with col2:
                        edit_l_hrs = st.number_input("Update Lecture Hours (L)", min_value=0, value=int(current_mod_data.get('lecture_hours', 3)))
                        edit_t_hrs = st.number_input("Update Tutorial Hours (T)", min_value=0, value=int(current_mod_data.get('tutorial_hours', 0)))
                        edit_p_hrs = st.number_input("Update Practical Hours (P)", min_value=0, value=int(current_mod_data.get('practical_hours', 0)))
                        
                    st.write("Actions:")
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Update Module", use_container_width=True):
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE Modules 
                                SET module_name=?, duration=?, lecture_hours=?, tutorial_hours=?, practical_hours=? 
                                WHERE module_code=?
                            ''', (edit_m_name, edit_duration, edit_l_hrs, edit_t_hrs, edit_p_hrs, selected_mod_id))
                            conn.commit()
                            st.success("Module updated successfully!")
                            st.rerun()
                            
                    with btn_col2:
                        if st.button("Delete Module", type="primary", use_container_width=True):
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM Modules WHERE module_code=?", (selected_mod_id,))
                            cursor.execute("DELETE FROM Allocations WHERE module_code=?", (selected_mod_id,))
                            conn.commit()
                            st.warning("Module deleted from system!")
                            st.rerun()

            st.divider()
            
            # This is an updated version of the bulk import document, this one was designed to bypass the format error within UTM's timetable, there is one standard format and one to skip the rows error format.
            st.subheader("📥 Bulk Import / Update Modules")
            st.info("Upload a standard module list or the official UTM timetable to auto-update module records.")
            
            format_choice = st.radio("Select Excel Format:", ["Standard Clean Format", "UTM Official Format (Skips 7 rows)"], horizontal=True, key="tab2_format")
            
            uploaded_file = st.file_uploader("Upload Modules Excel file", type=["xlsx", "xls"], key="module_uploader")
            if uploaded_file is not None:
                try:
                    if "UTM" in format_choice:
                        mod_df = pd.read_excel(uploaded_file, header=7)
                        col_code = 'Module Code'
                        col_name = 'Module Title'
                        col_prog = 'Programme'
                        col_coord = 'PROGRAMME COORDINATOR'
                        col_weight = 'Weightage'
                    else:
                        mod_df = pd.read_excel(uploaded_file)
                        col_code = 'Module Code'
                        col_name = 'Module Name'
                        col_prog = 'Programme'
                        col_coord = 'Coordinator'
                        col_weight = 'Weightage'
                        
                    st.write("File Preview:")
                    st.dataframe(mod_df.head())
                        
                    required_cols = [col_code, col_name]
                    missing_cols = [col for col in required_cols if col not in mod_df.columns]
                    
                    if missing_cols:
                        st.error(f"⚠️ Your file is missing these required columns: {', '.join(missing_cols)}")
                    else:
                        if st.button("Run Bulk Module Import", type="primary"):
                            cursor = conn.cursor()
                            import_count = 0
                            
                            for index, row in mod_df.iterrows():
                                code = str(row[col_code]).strip()
                                name = str(row[col_name]).strip()
                                
                                # Incase the row is empty it will safely skip it proceeding with the extraction.
                                if code == 'nan' or code == '': continue
                                
                                # Safe extraction with .get() (won't crash if columns are missing)
                                prog = str(row.get(col_prog, 'General')).strip()
                                coord = str(row.get(col_coord, 'Unassigned')).strip()
                                
                                try: weight = float(row.get(col_weight, 0))
                                except: weight = 0.0
                                
                                try: duration = int(row.get('Duration (Weeks)', 15))
                                except: duration = 15
                                
                                try: hours = int(row.get('Lecture Hours (L)', 3))
                                except: hours = 3
                                
                                try: tut_hours = int(row.get('Tutorial Hours (T)', 0))
                                except: tut_hours = 0
                                
                                try: prac_hours = int(row.get('Practical Hours (P)', 0))
                                except: prac_hours = 0
                                
                                cursor.execute("SELECT * FROM Modules WHERE module_code=?", (code,))
                                if cursor.fetchone():
                                    # This updates the already existing module.
                                    cursor.execute('''UPDATE Modules SET 
                                        module_name=?, duration=?, lecture_hours=?, tutorial_hours=?, practical_hours=?, 
                                        programme=?, programme_coordinator=?, weightage=? WHERE module_code=?''', 
                                        (name, duration, hours, tut_hours, prac_hours, prog, coord, weight, code))
                                else:
                                    # This creates a new module.
                                    cursor.execute('''INSERT INTO Modules 
                                        (module_code, module_name, duration, lecture_hours, tutorial_hours, practical_hours, programme, programme_coordinator, weightage) 
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                        (code, name, duration, hours, tut_hours, prac_hours, prog, coord, weight))
                                import_count += 1
                                
                            conn.commit()
                            st.success(f"✅ Successfully imported or updated {import_count} modules!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error processing file: {e}")
            
            st.divider()
            
            # This section allows the admin to manually add new modules using the module form import feature.
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
                        cursor.execute("INSERT INTO Modules (module_code, module_name, tutorial_hours, practical_hours) VALUES (?, ?, ?, ?)", 
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
            
            # Two semester tracking feature.
            # This enables the admin to be able to track the workload over two semesters timeline by switching between two radio button semester 1 and 2.
            selected_semester = st.radio("⏳ Select Active Semester to View:", ["Semester 1", "Semester 2"], horizontal=True)
            st.divider()
            
            # This is the smart workload calculator, it flags a lecturer if they exceeds their quota based off their roles and category.
            st.markdown(f"### Lecturer Workload Analysis ({selected_semester})")
            st.info("💡 Lecturers exceeding their category limit are highlighted automatically.")
            
            # The workload calculator will now operate based off the selected semester.
            workload_query = """
                SELECT u.name as "Lecturer", u.category_level as "Category", COUNT(a.module_code) as "Assigned Modules"
                FROM Users u
                LEFT JOIN Allocations a ON u.user_id = a.user_id AND a.semester = ?
                WHERE u.role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')
                GROUP BY u.user_id, u.name, u.category_level
            """
            workload_df = pd.read_sql_query(workload_query, conn, params=(selected_semester,))
            
            def get_category_limit(category):
                if pd.isna(category): return 99 
                if "Category 1 (Management)" in category: return 2
                if "Category 2 (Professional)" in category: return 1
                if "Category 3 (Technical)" in category: return 2
                if "Category 4 (PhD Staff)" in category: return 5
                if "Category 5 (Other Academic)" in category: return 6
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
            
            # This section is a detailed master list.
            st.markdown(f"### Detailed Master List ({selected_semester})")
            
            all_data = pd.read_sql_query("""
                SELECT u.name as "Lecturer", a.module_code as "Module Code", m.module_name as "Module Title", a.level_semester as "Cohort/Group", a.semester as "Semester"
                FROM Allocations a
                JOIN Users u ON a.user_id = u.user_id
                JOIN Modules m ON a.module_code = m.module_code
                WHERE a.semester = ?
            """, conn, params=(selected_semester,))
            
            lecturer_options = ["All Lecturers"] + sorted(all_data['Lecturer'].unique().tolist()) if not all_data.empty else ["All Lecturers"]
            selected_filter = st.selectbox("🔍 Search / Filter by Lecturer", lecturer_options)
            
            if selected_filter != "All Lecturers":
                display_data = all_data[all_data['Lecturer'] == selected_filter]
            else:
                display_data = all_data
                
            st.caption(f"Showing **{len(display_data)}** assigned module(s) for {selected_semester}.")
            st.dataframe(display_data, use_container_width=True, hide_index=True)
            
            st.divider()

            # This is the allocation tab section where the admin assigns modules to lecturers or remove them, etc...
            st.markdown("### Manual Assignment Control")
            
            if 'saved_staff_index' not in st.session_state:
                st.session_state.saved_staff_index = 0
                
            col1, col2 = st.columns(2)
            
            # Assigning a module to a staff.
            with col1:
                st.write("**Assign a Module to Staff**")
                
                with st.form("assign_form"):
                    staff_df = pd.read_sql_query("SELECT user_id, name FROM Users WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor', 'HoD', 'HoS')", conn)
                    
                    if staff_df.empty:
                        st.warning("⚠️ No teaching staff found.")
                        st.form_submit_button("Assign Module", disabled=True)
                    else:
                        staff_list = (staff_df['user_id'].astype(str) + " - " + staff_df['name']).tolist()
                        
                        if st.session_state.saved_staff_index >= len(staff_list):
                            st.session_state.saved_staff_index = 0
                            
                        selected_staff = st.selectbox("Select Staff Member", staff_list, index=st.session_state.saved_staff_index)
                        mod_df = pd.read_sql_query("SELECT module_code, module_name FROM Modules", conn)
                        
                        if mod_df.empty:
                            st.warning("⚠️ No modules found.")
                            st.form_submit_button("Assign Module", disabled=True)
                        else:
                            mod_list = mod_df['module_code'].astype(str) + " - " + mod_df['module_name']
                            selected_mod = st.selectbox("Select Module", mod_list)
                            
                            # Selecting between two semesters when assigning modules.
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
                                # This checks if a lecturer is already teaching this particular module in the current semester.
                                cursor.execute("SELECT * FROM Allocations WHERE user_id=? AND module_code=? AND level_semester=? AND semester=?", (s_id, m_id, assign_cohort, assign_semester))
                                if cursor.fetchone():
                                    st.error(f"This person is already teaching {m_id} for {assign_cohort} in {assign_semester}!")
                                else:
                                    # Insert the new record with the correct semester.
                                    cursor.execute("INSERT INTO Allocations (user_id, module_code, cohort, semester) VALUES (?, ?, ?, ?)", (s_id, m_id, assign_cohort, assign_semester))
                                    conn.commit()
                                    st.success(f"Assigned {m_id} ({assign_cohort}) to {assign_semester} successfully!")
                                    st.rerun()

            # This is to remove a module allocated to a staff.
            with col2:
                st.write("**Remove an Allocation**")
                with st.form("remove_form"):
                    alloc_df = pd.read_sql_query("""
                        SELECT a.user_id, u.name, a.module_code, m.module_name, a.level_semester, a.semester
                        FROM Allocations a
                        JOIN Users u ON a.user_id = u.user_id
                        JOIN Modules m ON a.module_code = m.module_code
                    """, conn)
                    
                    if not alloc_df.empty:
                        alloc_list = alloc_df['user_id'].astype(str) + "|" + alloc_df['module_code'] + "|" + alloc_df['level_semester'] + "|" + alloc_df['semester'] + " : " + alloc_df['name'] + " - " + alloc_df['module_name'] + " (" + alloc_df['level_semester'] + ", " + alloc_df['semester'] + ")"
                        selected_alloc = st.selectbox("Select Assignment to Remove", alloc_list)
                        
                        submit_remove = st.form_submit_button("Remove Allocation", type="primary", use_container_width=True)
                        
                        if submit_remove:
                            keys = selected_alloc.split(" : ")[0].split("|")
                            r_uid, r_mid, r_cohort, r_semester = int(keys[0]), keys[1], keys[2], keys[3]
                            
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM Allocations WHERE user_id=? AND module_code=? AND level_semester=? AND semester=?", (r_uid, r_mid, r_cohort, r_semester))
                            conn.commit()
                            st.success("Allocation removed successfully!")
                            st.rerun()
                    else:
                        st.info("There are no allocations to remove.")
                        st.form_submit_button("Remove Allocation", disabled=True)

            # This is the bulk import feature to import the Timetable along with allocations,etc...
            st.divider()
            st.markdown("### 📥 Bulk Import Timetable (Allocations & Enrichment)")
            st.info("Upload the timetable. The system will auto-assign modules AND enrich staff/module profiles with FT/PT, Weightage, and Student Counts.")
            
            format_choice = st.radio("Select Excel File Format:", ["UTM Official Format (Skips 7 rows)", "Standard Clean Format"], horizontal=True)
            
            uploaded_tt = st.file_uploader("Choose a Timetable Excel file", type=["xlsx", "xls"], key="tt_upload")
            
            if uploaded_tt is not None:
                try:
                    if "UTM" in format_choice:
                        tt_df = pd.read_excel(uploaded_tt, header=7)
                        # UTM timetable columns mapping
                        col_resource = 'Resource Person\nSURNAME Name (Title)'
                        col_module = 'Module Code'
                        col_mod_title = 'Module Title'
                        col_cohort = 'Cohort'
                        col_level = 'Level Sem\ne.g L1S2'
                        col_dept = 'Dept'
                        col_prog = 'Programme'
                        col_students = 'No. of Students'
                        col_coord = 'PROGRAMME COORDINATOR'
                        col_weight = 'Weightage'
                        col_ftpt = 'FT/PT'
                    else:
                        tt_df = pd.read_excel(uploaded_tt)
                        # Clean format version of Timetable columns mapping
                        col_resource = 'Resource person Name'
                        col_module = 'Module Code'
                        col_mod_title = 'Module Name'
                        col_cohort = 'Cohort'
                        col_level = 'Semester'
                        col_dept = 'Department'
                        col_prog = 'Programme'
                        col_students = 'Students'
                        col_coord = 'Coordinator'
                        col_weight = 'Weightage'
                        col_ftpt = 'FT/PT'
                        
                    st.write("File Preview:")
                    st.dataframe(tt_df.head(), use_container_width=True)
                    
                    required_cols = [col_resource, col_module, col_level]
                    missing_cols = [col for col in required_cols if col not in tt_df.columns]
                    
                    if missing_cols:
                        st.error(f"⚠️ Your Excel file is missing these required core columns: {', '.join(missing_cols)}")
                    else:
                        if st.button("Run Enterprise Bulk Import", type="primary", use_container_width=True):
                            cursor = conn.cursor()
                            alloc_count = 0
                            missing_staff = set()
                            
                            for index, row in tt_df.iterrows():
                                raw_name = str(row[col_resource]).strip()
                                if raw_name == 'nan' or raw_name == '' or pd.isna(row[col_resource]):
                                    continue
                                
                                # 1. Extract Title and Clean Name
                                title = ""
                                staff_name = raw_name
                                if "(" in raw_name and ")" in raw_name:
                                    title = raw_name.split("(")[1].split(")")[0].strip() # Extracts 'Mr', 'Dr', etc.
                                    staff_name = raw_name.split("(")[0].strip()
                                
                                # 2. Safely Extract New Enterprise Data
                                mod_code = str(row[col_module]).strip()
                                mod_title = str(row.get(col_mod_title, 'Unknown')).strip()
                                
                                # Rmoved the Nan default value assigned by Pandas to something more streamline to the UTM's timetable
                                if mod_title.lower() == 'nan':
                                    mod_title = 'Unknown Title'
                                    
                                cohort = str(row.get(col_cohort, 'Group A')).strip() 
                                dept = str(row.get(col_dept, 'Unassigned')).strip()
                                prog = str(row.get(col_prog, 'General')).strip()
                                coord = str(row.get(col_coord, 'Unassigned')).strip()
                                ftpt = str(row.get(col_ftpt, 'FT')).strip()
                                
                                # convertion of numbers in a safe way
                                try: weight = float(row.get(col_weight, 0))
                                except: weight = 0.0
                                
                                try: students = int(row.get(col_students, 0))
                                except: students = 0
                                
                                # A feature to know which semester we are in and sort in two separate semesters overview.
                                level_sem = str(row[col_level]).upper()
                                if "UTM" in format_choice:
                                    semester = "Semester 2" if 'S2' in level_sem else "Semester 1"
                                else:
                                    semester = str(row[col_level]).strip()
                                
                                # Added changes to update database since there were missing factors from the timetable
                                
                                # Filling the empty slots with default values and update already existing ones.
                                cursor.execute("SELECT module_code, module_name FROM Modules WHERE module_code=?", (mod_code,))
                                existing_mod = cursor.fetchone()
                                
                                if existing_mod:
                                    # Fixing the nan error occured in Name column.
                                    if str(existing_mod[1]).lower() == 'nan' and mod_title != 'Unknown Title':
                                        cursor.execute("UPDATE Modules SET module_name=?, programme=?, weightage=?, programme_coordinator=? WHERE module_code=?", (mod_title, prog, weight, coord, mod_code))
                                    else:
                                        cursor.execute("UPDATE Modules SET programme=?, weightage=?, programme_coordinator=? WHERE module_code=?", (prog, weight, coord, mod_code))
                                else:
                                    # Adding default values for hours instead of saying none.
                                    cursor.execute("""
                                        INSERT INTO Modules (module_code, module_name, duration, lecture_hours, tutorial_hours, practical_hours, programme, weightage, programme_coordinator) 
                                        VALUES (?, ?, 15, 3, 0, 0, ?, ?, ?)
                                    """, (mod_code, mod_title, prog, weight, coord))

                                # Step B: Match User and Enrich Profile 
                                cursor.execute("SELECT user_id FROM Users WHERE name LIKE ?", (f"%{staff_name}%",))
                                user_result = cursor.fetchone()
                                
                                if user_result:
                                    s_id = user_result[0]
                                    
                                    # Update the lecturer's profile with their true department and FT/PT status!
                                    cursor.execute("UPDATE Users SET department=?, title=?, employment_type=? WHERE user_id=?", (dept, title, ftpt, s_id))
                                    
                                    # Step C: Log the Allocation with Student Counts
                                    cursor.execute("SELECT * FROM Allocations WHERE user_id=? AND module_code=? AND level_semester=? AND semester=?", (s_id, mod_code, cohort, semester))
                                    if not cursor.fetchone():
                                        cursor.execute("INSERT INTO Allocations (user_id, module_code, level_semester, semester, students_count) VALUES (?, ?, ?, ?, ?)", (s_id, mod_code, level_sem, semester, students))
                                        alloc_count += 1
                                else:
                                    missing_staff.add(staff_name)
                                            
                            conn.commit()
                            st.success(f"🎉 Success! Imported {alloc_count} new allocations and enriched system database with UTM data!")
                            
                            if missing_staff:
                                st.warning(f"⚠️ Could not auto-match these names to the database: {', '.join(missing_staff)}. Please ensure they are registered in Tab 1.")
                                
                except Exception as e:
                    st.error(f"Error processing timetable: {e}")

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
                                    # Move the ticket to the HoD's desk!
                                    cursor.execute("UPDATE Pending_Promotions SET status = 'Pending HoD', rejection_reason = '' WHERE ticket_id = ?", (view_ticket,))
                                    st.success(f"Ticket #{view_ticket} verified and forwarded to the HoD!")
                                else:
                                    # Kick it back to the Lecturer
                                    cursor.execute("UPDATE Pending_Promotions SET status = 'Rejected', rejection_reason = ? WHERE ticket_id = ?", (rejection_reason, view_ticket))
                                    st.warning(f"Ticket #{view_ticket} has been rejected and sent back to the applicant.")
                                    
                                conn.commit()
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
            SELECT m.module_code as "Code", m.module_name as "Module Title", m.programme as "Programme", m.programme_coordinator as "Coordinator", m.weightage as "Weightage", m.lecture_hours as "L", m.tutorial_hours as "T", m.practical_hours as "P"
            FROM Allocations a
            JOIN Modules m ON a.module_code = m.module_code
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

        # --- SECTION: UPGRADED PROMOTION MANAGEMENT ---
        st.subheader("🚀 Promotion Management")
        
        cursor = conn.cursor()
        
        # 1. Check for ACTIVE tickets to see if we should hide the form
        cursor.execute("""
            SELECT COUNT(*) FROM Pending_Promotions 
            WHERE user_id = ? AND status NOT IN ('Approved', 'Rejected')
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
                    
                    # --- NEW: THE PDF UPLOADER ---
                    st.info("📄 Please attach your official Registration Letter to proceed.")
                    reg_letter = st.file_uploader("Upload Registration Letter (PDF only)", type=["pdf"])
                    
                    if st.form_submit_button("Submit Application"):
                        # Safety Catch: Block them if they forgot the PDF!
                        if reg_letter is None:
                            st.error("⚠️ You must upload your PDF Registration Letter to apply.")
                        else:
                            # Convert the PDF into raw binary data so it can live in the database
                            letter_bytes = reg_letter.read()
                            
                            cursor.execute("SELECT MAX(ticket_id) FROM Pending_Promotions")
                            max_id_result = cursor.fetchone()[0]
                            new_ticket_id = 1 if max_id_result is None else int(max_id_result) + 1
                            
                            # Save the application AND the PDF file at the same time
                            cursor.execute("""
                                INSERT INTO Pending_Promotions (ticket_id, user_id, proposed_role, proposed_category, status, rejection_reason, registration_letter)
                                VALUES (?, ?, ?, ?, 'Pending Registry', '', ?)
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
            FROM Pending_Promotions 
            WHERE user_id = ?
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

        # --- SECTION: ENTERPRISE WORKLOAD & HISTORICAL LOG ---
        st.subheader("📚 My Teaching Workload")
        
        cursor = conn.cursor()
        
        # UPGRADED SQL: Now fetches Programme, Coordinator, Lecture Hours, and FT/PT!
        my_modules_query = """
            SELECT a.semester as "Semester", 
                   a.module_code as "Module Code", 
                   m.module_name as "Module Title", 
                   m.programme as "Programme",
                   a.level_semester as "Cohort", 
                   u.employment_type as "FT/PT",
                   m.lecture_hours as "L. Hrs",
                   a.students_count as "Students", 
                   m.weightage as "Weightage",
                   m.programme_coordinator as "Coordinator"
            FROM Allocations a
            JOIN Modules m ON a.module_code = m.module_code
            JOIN Users u ON a.user_id = u.user_id
            WHERE a.user_id = ?
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
            
            # --- NEW: WORKLOAD PDF EXPORT ---
            st.write("### 🖨️ Export Official Workload Report")
            st.info("Download a formatted PDF summary of your entire workload across all semesters for board meetings and records.")
            
            # Fetch User Details for the PDF Header
            user_data = cursor.execute("SELECT name, role FROM Users WHERE user_id = ?", (st.session_state.user_id,)).fetchone()
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
                
                # Table Header
                pdf.set_font("Arial", "B", 10)
                pdf.set_fill_color(200, 200, 200) # Light Gray background for the header
                pdf.cell(25, 10, "Semester", border=1, fill=True)
                pdf.cell(25, 10, "Code", border=1, fill=True)
                pdf.cell(80, 10, "Module Title", border=1, fill=True)
                pdf.cell(30, 10, "Cohort", border=1, fill=True)
                pdf.cell(30, 10, "Students", border=1, fill=True, ln=True)
                
                # Table Body
                pdf.set_font("Arial", "", 9)
                for index, row in df.iterrows():
                    pdf.cell(25, 10, str(row['Semester']), border=1)
                    pdf.cell(25, 10, str(row['Module Code']), border=1)
                    
                    # Ensure long module titles don't break the table boundaries
                    title = str(row['Module Title'])
                    if len(title) > 42: title = title[:39] + "..."
                    pdf.cell(80, 10, title, border=1)
                    
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
        
        # Make sure your tab variables match this list!
        tab1, tab2, tab3 = st.tabs(["Overview", "Promotion Approvals", "Department Analytics"])
        
        # --- TAB 1: ALLOCATIONS OVERVIEW & METRICS ---
        with tab1:
            st.subheader("Department Workload & Metrics")
            conn = sqlite3.connect('registry_database.db')
            try:
                # --- NEW: SYSTEM ALERTS (QUOTAS & PROMOTIONS) ---
                # We use the exact same SQL logic as the Registry to guarantee matching math
                alert_query = """
                    SELECT u.name as "Staff Member", u.category_level as "Category", COUNT(a.module_code) as "Assigned Modules"
                    FROM Users u
                    LEFT JOIN Allocations a ON u.user_id = a.user_id
                    WHERE u.role != 'Registry Officer'
                    GROUP BY u.user_id
                """
                alert_df = pd.read_sql_query(alert_query, conn)
                
                # Create an empty list to store ONLY the people who exceed limits or hit promotions
                flagged_data = []
                
                for index, row in alert_df.iterrows():
                    cat = str(row['Category'])
                    assigned = int(row['Assigned Modules'])
                    
                    # Define dynamic limits exactly like the Registry constraints
                    limit = 99
                    if "Category 1 (Management)" in cat: limit = 2
                    elif "Category 2 (Professional)" in cat: limit = 1
                    elif "Category 3 (Technical)" in cat: limit = 2
                    elif "Category 4 (PhD Staff)" in cat: limit = 5
                    elif "Category 5 (Other Academic)" in cat: limit = 6
                    
                    # If they hit the limits, we add them to the flagged list
                    if assigned > limit:
                        flagged_data.append({
                            "Staff Member": row['Staff Member'],
                            "Category": cat,
                            "Assigned": assigned,
                            "Limit": limit,
                            "Alert Type": "🚨 OVERLOAD"
                        })
                    elif assigned == limit and limit != 99:
                        flagged_data.append({
                            "Staff Member": row['Staff Member'],
                            "Category": cat,
                            "Assigned": assigned,
                            "Limit": limit,
                            "Alert Type": "✅ PROMOTION ELIGIBLE"
                        })
                
                # If the list has people in it, draw the clean Alert Table
                if flagged_data:
                    st.write("### 🚨 Staff Quota Alerts")
                    flag_df = pd.DataFrame(flagged_data)
                    
                    # Add background colors based on the alert type
                    def highlight_alerts(row):
                        if row['Alert Type'] == '🚨 OVERLOAD':
                            return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
                        elif row['Alert Type'] == '✅ PROMOTION ELIGIBLE':
                            return ['background-color: rgba(75, 255, 75, 0.2)'] * len(row)
                        return [''] * len(row)
                    
                    styled_flag_df = flag_df.style.apply(highlight_alerts, axis=1)
                    st.dataframe(styled_flag_df, use_container_width=True, hide_index=True)
                else:
                    st.info("✅ All staff workloads are within normal limits. No pending promotion quotas met.")
                
                st.divider()
                # --- END OF SYSTEM ALERTS ---

                # --- 1. GLOBAL SEMESTER FILTER ---
                selected_semester = st.radio("⏳ Select Semester to Analyze:", ["Semester 1", "Semester 2"], horizontal=True, key="hod_sem")
                st.divider()

                # --- 2. ENTERPRISE METRICS ---
                # Calculate high-level stats for the selected semester
                staff_count = conn.execute("SELECT COUNT(*) FROM Users WHERE role IN ('Lecturer', 'Senior Lecturer', 'Associate Professor', 'Professor')").fetchone()[0]
                
                sem_stats = conn.execute("""
                    SELECT COUNT(a.module_code, SUM(a.students_count), SUM(m.weightage)
                    FROM Allocations a
                    JOIN Modules m ON a.module_code = m.module_code
                    WHERE a.semester = ?
                """, (selected_semester,)).fetchone()
                
                mod_count = sem_stats[0] if sem_stats[0] else 0
                student_count = sem_stats[1] if sem_stats[1] else 0
                total_weight = sem_stats[2] if sem_stats[2] else 0
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Teaching Staff", staff_count)
                m2.metric("Assigned Modules", mod_count)
                m3.metric("Total Students", student_count)
                m4.metric("Total Weightage", total_weight)
                
                st.divider()

                # --- 3. YOUR DUAL-FILTER SYSTEM (UPGRADED) ---
                st.write(f"### Detailed Allocations ({selected_semester})")
                
                # Upgraded SQL: Now pulls the new UTM data but filters by the radio button!
                alloc_df = pd.read_sql_query("""
                    SELECT u.name as "Lecturer", u.employment_type as "FT/PT", 
                           a.module_code as "Module Code", m.module_name as "Module Title", 
                           a.level_semester as "Cohort", a.students_count as "Students", m.weightage as "Weightage"
                    FROM Allocations a
                    JOIN Users u ON a.user_id = u.user_id
                    JOIN Modules m ON a.module_code = m.module_code
                    WHERE a.semester = ?
                """, conn, params=(selected_semester,))
                
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
                    
                # Upgraded Dynamic Metrics: Now shows Student totals for the filtered view!
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

                    # --- NEW: REVIEW APPLICATION LETTER SECTION ---
                    st.write("### 📄 Review Application Letter")
                    view_ticket = st.selectbox("Select Ticket ID to Download Letter:", promo_df['ticket_id'], key="hod_letter_select")
                    
                    # Fetch the PDF BLOB from the database
                    cursor = conn.execute("SELECT u.name, p.registration_letter FROM Pending_Promotions p JOIN Users u ON p.user_id = u.user_id WHERE p.ticket_id = ?", (int(view_ticket),))
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
                    # --- END NEW SECTION ---

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

        # --- TAB 3: DEPARTMENT ANALYTICS ---
        with tab3:
            st.subheader("📈 Department Workload & Analytics")
            conn = sqlite3.connect('registry_database.db')
            
            try:
                # --- 1. HIGH-LEVEL METRICS (PRESERVED) ---
                col1, col2 = st.columns(2)
                
                # Count total teaching staff and active tickets waiting for the HoD
                total_staff = pd.read_sql_query("SELECT COUNT(*) FROM Users WHERE category_level IN ('Category 4 (PhD Staff)', 'Category 5 (Other Academic)')", conn).iloc[0,0]
                pending_hod = pd.read_sql_query("SELECT COUNT(*) FROM Pending_Promotions WHERE status = 'Pending HoD'", conn).iloc[0,0]
                
                col1.metric("Total Teaching Staff", total_staff)
                col2.metric("Pending HoD Reviews", pending_hod)
                
                st.divider()
                
                # --- 2. DUAL-SEMESTER WORKLOAD DISTRIBUTION CHART (UPGRADED) ---
                st.write("### 📊 Annual Workload Comparison")
                st.info("Displays the total module workload for each teaching staff member, split by semester.")
                
                # Upgraded Query: Added a.semester to the SELECT and GROUP BY to enable the dual-color split
                chart_query = """
                    SELECT u.name as "Staff Member", a.semester, COUNT(a.module_code) as "Module Count"
                    FROM Users u
                    JOIN Allocations a ON u.user_id = a.user_id
                    WHERE u.category_level IN ('Category 4 (PhD Staff)', 'Category 5 (Other Academic)')
                    GROUP BY u.name, a.semester
                """
                chart_df = pd.read_sql_query(chart_query, conn)
                
                if not chart_df.empty:
                    # Pivot the data: Staff names on the left (index), Semester 1 & 2 as side-by-side columns
                    chart_data = chart_df.pivot(index='Staff Member', columns='semester', values='Module Count').fillna(0)
                    
                    # Streamlit automatically assigns unique, contrasting colors to the trend lines!
                    st.line_chart(chart_data, use_container_width=True)
                else:
                    st.info("No workload data available to chart.")
                    
            except Exception as e:
                st.error(f"Error loading analytics: {e}")
                
            conn.close()

    # --- TABBED HOS VIEW ---
    def hos_dashboard():
        st.title("🏛️ Head of School Dashboard")
        st.write("Finalize staff promotions and oversee school-wide metrics.")
        
        tab1, tab2 = st.tabs(["Final Promotion Approvals", "School Overview"])
        
        # --- TAB 1: EXECUTIVE OVERVIEW & PROMOTIONS ---
        with tab1:
            st.subheader("School Executive Overview")
            conn = sqlite3.connect('registry_database.db')
            try:
                # ==========================================
                # SECTION A: THE NEW ENTERPRISE METRICS
                # ==========================================
                selected_semester = st.radio("⏳ Select Semester to Analyze:", ["Semester 1", "Semester 2"], horizontal=True, key="hos_sem")
                st.divider()
                
                # School-Wide Metrics
                dept_count = conn.execute("SELECT COUNT(DISTINCT department) FROM Users WHERE department != 'Unassigned'").fetchone()[0]
                prog_count = conn.execute("SELECT COUNT(DISTINCT programme) FROM Modules WHERE programme != 'General'").fetchone()[0]
                
                school_stats = conn.execute("""
                    SELECT COUNT(a.module_code), SUM(a.students_count)
                    FROM Allocations a
                    WHERE a.semester = ?
                """, (selected_semester,)).fetchone()
                
                total_classes = school_stats[0] if school_stats[0] else 0
                total_students = school_stats[1] if school_stats[1] else 0
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Active Departments", dept_count)
                col2.metric("Active Programmes", prog_count)
                col3.metric("Running Classes", total_classes)
                col4.metric("Student Enrollments", total_students)
                
                st.divider()
                
                # Department Performance Table
                st.write(f"### Department Performance ({selected_semester})")
                dept_df = pd.read_sql_query("""
                    SELECT 
                        u.department as "Department",
                        COUNT(DISTINCT u.user_id) as "Staff Count",
                        COUNT(a.module_code) as "Modules Taught",
                        SUM(a.students_count) as "Total Students",
                        SUM(m.weightage) as "Total Weightage"
                    FROM Users u
                    LEFT JOIN Allocations a ON u.user_id = a.user_id AND a.semester = ?
                    LEFT JOIN Modules m ON a.module_code = m.module_code
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

                    # --- NEW: REVIEW APPLICATION LETTER SECTION ---
                    st.write("### 📄 Review Application Letter")
                    view_ticket = st.selectbox("Select Ticket ID to Download Letter:", promo_df['ticket_id'], key="hos_letter_select")
                    
                    # Fetch the PDF BLOB from the database
                    cursor = conn.execute("SELECT u.name, p.registration_letter FROM Pending_Promotions p JOIN Users u ON p.user_id = u.user_id WHERE p.ticket_id = ?", (int(view_ticket),))
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
                    # --- END NEW SECTION ---

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
                                    cursor.execute("SELECT user_id, proposed_role, proposed_category FROM Pending_Promotions WHERE ticket_id = ?", (selected_ticket,))
                                    ticket_data = cursor.fetchone()
                                    target_user_id = ticket_data[0]
                                    new_role = ticket_data[1]
                                    new_category = ticket_data[2]
                                    
                                    cursor.execute("UPDATE Users SET role = ?, category_level = ? WHERE user_id = ?", (new_role, new_category, target_user_id))
                                    cursor.execute("UPDATE Pending_Promotions SET status = 'Approved', rejection_reason = '' WHERE ticket_id = ?", (selected_ticket,))
                                    st.success(f"Promotion Approved! The applicant's official role has been updated to {new_role}.")
                                else:
                                    cursor.execute("UPDATE Pending_Promotions SET status = 'Rejected', rejection_reason = ? WHERE ticket_id = ?", (rejection_reason, selected_ticket))
                                    st.warning(f"Ticket #{selected_ticket} has been Rejected.")
                                    
                                conn.commit()
                                st.rerun()
                
            except Exception as e:
                st.error(f"Error loading dashboard: {e}")
            conn.close()

        # --- TAB 2: SCHOOL OVERVIEW (VISUAL ANALYTICS) ---
        with tab2:
            st.subheader("📊 School Analytics & Demographics")
            conn = sqlite3.connect('registry_database.db')
            
            try:
                # 1. High-Level Metrics (Top Row)
                col1, col2, col3 = st.columns(3)
                
                # Fetching live counts from the database
                total_staff = pd.read_sql_query("SELECT COUNT(*) FROM Users WHERE role != 'Registry Officer'", conn).iloc[0,0]
                total_modules = pd.read_sql_query("SELECT COUNT(*) FROM Modules", conn).iloc[0,0]
                pending_promos = pd.read_sql_query("SELECT COUNT(*) FROM Pending_Promotions WHERE status = 'Pending HoS'", conn).iloc[0,0]
                
                col1.metric("Total Academic Staff", total_staff)
                col2.metric("Total Active Modules", total_modules)
                col3.metric("Pending Final Approvals", pending_promos)
                
                st.divider()
                
                # 2. Visual Charts (Middle Row)
                st.write("### Staff Distribution by Role")
                
                # Query to group staff by role
                role_df = pd.read_sql_query("""
                    SELECT role, COUNT(user_id) as Count 
                    FROM Users 
                    WHERE role != 'Registry Officer' 
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
                    FROM Users u
                    LEFT JOIN Allocations a ON u.user_id = a.user_id
                    WHERE u.role != 'Registry Officer'
                    GROUP BY u.user_id
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

