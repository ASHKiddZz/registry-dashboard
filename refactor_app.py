def refactor_codebase():
    print("⏳ Scanning app.py for legacy schema...")
    
    with open('app.py', 'r', encoding='utf-8') as file:
        code = file.read()

    # 1. Fix the SQL SELECT and JOIN references
    code = code.replace("a.cohort", "a.level_semester")
    code = code.replace("a.module_id", "a.module_code")
    code = code.replace("m.module_id", "m.module_code")

    # 2. Fix Pandas DataFrame dictionary references
    code = code.replace("['cohort']", "['level_semester']")
    code = code.replace("['module_id']", "['module_code']")

    # 3. Fix the WHERE clauses
    code = code.replace("cohort=?", "level_semester=?")
    code = code.replace("module_id=?", "module_code=?")

    # 4. Fix the bulk upload Allocations INSERT (removes duplicate cohort column)
    code = code.replace(
        "INSERT INTO Allocations (user_id, module_id, cohort, semester, level_semester, students_count) VALUES (?, ?, ?, ?, ?, ?)",
        "INSERT INTO Allocations (user_id, module_code, level_semester, semester, students_count) VALUES (?, ?, ?, ?, ?)"
    )
    code = code.replace(
        "(s_id, mod_code, cohort, semester, level_sem, students)",
        "(s_id, mod_code, level_sem, semester, students)"
    )

    # 5. Fix the Modules INSERT 
    code = code.replace(
        "INSERT INTO Modules (module_id, module_name, duration, lecture_hours, tutorial_hours, practical_hours) VALUES (?, ?, ?, ?, ?, ?)",
        "INSERT INTO Modules (module_code, module_name, tutorial_hours, practical_hours) VALUES (?, ?, ?, ?)"
    )
    code = code.replace(
        "(m_id, m_name, d_hrs, l_hrs, t_hrs, p_hrs)",
        "(m_id, m_name, t_hrs, p_hrs)"
    )

    # 6. Fix the Modules UPDATE 
    code = code.replace(
        "UPDATE Modules SET module_name=?, duration=?, lecture_hours=?, tutorial_hours=?, practical_hours=? WHERE module_id=?",
        "UPDATE Modules SET module_name=?, tutorial_hours=?, practical_hours=? WHERE module_code=?"
    )
    code = code.replace(
        "(edit_name, edit_duration, edit_lecture, edit_tutorial, edit_practical, selected_mod_id)",
        "(edit_name, edit_tutorial, edit_practical, selected_mod_id)"
    )

    # Save the cleaned code
    with open('app.py', 'w', encoding='utf-8') as file:
        file.write(code)

    print("✅ SUCCESS! app.py has been permanently scrubbed and updated to the Cloud Schema!")

if __name__ == "__main__":
    refactor_codebase()