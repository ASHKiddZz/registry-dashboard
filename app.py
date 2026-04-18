import streamlit as st
import sqlite3
import pandas as pd

# 1. Setup the Page
st.set_page_config(page_title="Registry Workload System", layout="wide")

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
    if st.session_state.user_role == "Registry Officer":
        tab1, tab2, tab3 = st.tabs(["Manage Users", "Manage Modules", "Allocations Overview"])
        
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
                    
                    roles = ["Lecturer", "HOD", "HOS", "Registry Officer"]
                    current_role = current_data['role']
                    role_index = roles.index(current_role) if current_role in roles else 0
                    edit_role = st.selectbox("Update Role", roles, index=role_index)
                    
                with col2:
                    levels = ["Cat 1 - HoS", "Cat 4 - Staff enrolled in PhD", "Cat 5 - All other Academic", "N/A"]
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
                new_role = st.selectbox("Role", ["Lecturer", "HOD", "HOS", "Registry Officer"])
                new_level = st.selectbox("Category Limit", ["Cat 1 - HoS", "Cat 4 - Staff enrolled in PhD", "Cat 5 - All other Academic", "N/A"])
                new_pass = st.text_input("Temporary Password", type="password")
                
                submit_user = st.form_submit_button("Create Account")
                
                if submit_user:
                    if new_name and new_pass:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO Users (name, role, category_level, password) VALUES (?, ?, ?, ?)", 
                                       (new_name, new_role, new_level, new_pass))
                        conn.commit()
                        st.success(f"Account created for {new_name}!")
                        st.rerun()
                    else:
                        st.error("Please fill out the Name and Password fields.")
            conn.close()

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
                        edit_duration = st.number_input("Update Duration (Weeks)", min_value=1, value=int(current_mod_data['duration']))
                        
                    with col2:
                        edit_l_hrs = st.number_input("Update Lecture Hours (L)", min_value=0, value=int(current_mod_data['lecture_hours']))
                        edit_t_hrs = st.number_input("Update Tutorial Hours (T)", min_value=0, value=int(current_mod_data['tutorial_hours']))
                        edit_p_hrs = st.number_input("Update Practical Hours (P)", min_value=0, value=int(current_mod_data['practical_hours']))
                        
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
                WHERE u.role IN ('Lecturer', 'HOD', 'HOS')
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
                    staff_df = pd.read_sql_query("SELECT user_id, name FROM Users WHERE role IN ('Lecturer', 'HOD', 'HOS')", conn)
                    
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

    # --- LECTURER VIEW ---
    elif st.session_state.user_role == "Lecturer":
        st.info("Personal Workload Summary")
        conn = sqlite3.connect('registry_database.db')
        my_data = pd.read_sql_query("""
            SELECT m.module_id as "Code", m.module_name as "Module Title", 
                   m.lecture_hours as "L", m.practical_hours as "P"
            FROM Allocations a
            JOIN Modules m ON a.module_id = m.module_id
            WHERE a.user_id = ?
        """, conn, params=(st.session_state.user_id,))
        conn.close()

        if not my_data.empty:
            st.dataframe(my_data, use_container_width=True, hide_index=True)
        else:
            st.warning("No modules assigned to your account yet.")