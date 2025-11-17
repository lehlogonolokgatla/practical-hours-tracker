# practrack_v2_final_client_ready.py
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, time
import io
import pandas.io.excel

# Use session state to manage temporary messages
if 'message' not in st.session_state:
    st.session_state.message = None

DB_PATH = "practical_hours.db"


# -------------------------------
# DB INITIALIZATION
# -------------------------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        # Students table - Includes student_initials for new DBs
        c.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                student_initials TEXT,
                student_id TEXT UNIQUE NOT NULL
            )
        ''')

        # --- DB Migration Check (Ensures schema is correct) ---
        try:
            c.execute("SELECT student_initials FROM students LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE students ADD COLUMN student_initials TEXT")
        # --------------------------

        # Practical hours log (No change)
        c.execute('''
            CREATE TABLE IF NOT EXISTS hours_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecturer_name TEXT,
                student_name TEXT,
                student_id TEXT,
                site TEXT,
                date TEXT,
                start_time TEXT,
                end_time TEXT,
                total_hours REAL,
                notes TEXT
            )
        ''')
        # Site requirements (No change)
        c.execute('''
            CREATE TABLE IF NOT EXISTS site_requirements (
                site_name TEXT PRIMARY KEY,
                required_hours REAL NOT NULL
            )
        ''')
        # Default sites
        default_sites = [
            ("Site A - Hospital A", 120.0),
            ("Site B - Clinic B", 80.0),
            ("Site C - Laboratory C", 60.0),
            ("Site D - Community D", 40.0)
        ]
        for site_name, req in default_sites:
            c.execute('INSERT OR IGNORE INTO site_requirements (site_name, required_hours) VALUES (?, ?)',
                      (site_name, req))
        conn.commit()


init_db()


# -------------------------------
# DB HELPER FUNCTIONS
# -------------------------------
def run_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(query, params)
        if fetch:
            return c.fetchall()
        conn.commit()


def get_students_df():
    df = pd.DataFrame(run_query("SELECT * FROM students ORDER BY student_name", fetch=True),
                      columns=['id', 'student_name', 'student_initials', 'student_id'])
    if not df.empty:
        df['student_id'] = df['student_id'].astype(str)
    return df


def get_sites_df():
    return pd.DataFrame(run_query("SELECT * FROM site_requirements", fetch=True),
                        columns=['site_name', 'required_hours'])


def get_records_df():
    return pd.DataFrame(run_query("SELECT * FROM hours_log ORDER BY date DESC, student_name", fetch=True),
                        columns=['id', 'lecturer_name', 'student_name', 'student_id', 'site', 'date', 'start_time',
                                 'end_time', 'total_hours', 'notes'])


def add_student(student_name, student_initials, student_id):
    try:
        student_id = str(student_id).strip()
        run_query("INSERT INTO students (student_name, student_initials, student_id) VALUES (?, ?, ?)",
                  (student_name, student_initials, student_id))
        return True, "Student added"
    except sqlite3.IntegrityError:
        return False, f"Student ID {student_id} already exists"


def update_student(student_id, new_name):
    run_query("UPDATE students SET student_name=? WHERE student_id=?", (new_name, student_id))
    run_query("UPDATE hours_log SET student_name=? WHERE student_id=?", (new_name, student_id))


def delete_student(student_id):
    run_query("DELETE FROM students WHERE student_id=?", (student_id,))
    run_query("DELETE FROM hours_log WHERE student_id=?", (student_id,))


def set_site_requirement(site_name, required_hours):
    run_query("INSERT OR REPLACE INTO site_requirements (site_name, required_hours) VALUES (?, ?)",
              (site_name, required_hours))


def add_hours_log(lecturer, student_name, student_id, site, date, start_time, end_time, total_hours, notes):
    run_query('''
        INSERT INTO hours_log (lecturer_name, student_name, student_id, site, date, start_time, end_time, total_hours, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (lecturer, student_name, student_id, site, date, start_time, end_time, total_hours, notes))


def calculate_summary():
    students = get_students_df()
    sites = get_sites_df()
    records = get_records_df()
    if students.empty:
        return pd.DataFrame()
    rows = []
    for _, s in students.iterrows():
        row = {"Student Name": s['student_name'], "Student ID": s['student_id']}
        for _, site in sites.iterrows():
            completed = records[(records['student_id'] == s['student_id']) & (records['site'] == site['site_name'])]
            total_completed = completed['total_hours'].sum() if not completed.empty else 0
            row[f"{site['site_name']} - Completed"] = round(total_completed, 2)
            row[f"{site['site_name']} - Required"] = site['required_hours']
            row[f"{site['site_name']} - Owed"] = round(site['required_hours'] - total_completed, 2)
        rows.append(row)
    return pd.DataFrame(rows)


# Handles the Excel export engine fallbacks
def to_excel_bytes(dfs_dict):
    output = io.BytesIO()
    try:
        engine = 'xlsxwriter'
        with pd.ExcelWriter(output, engine=engine) as writer:
            for sheet_name, df in dfs_dict.items():
                df.to_excel(writer, index=False, sheet_name=sheet_name)
    except Exception:
        try:
            engine = 'openpyxl'
            with pd.ExcelWriter(output, engine=engine) as writer:
                for sheet_name, df in dfs_dict.items():
                    df.to_excel(writer, index=False, sheet_name=sheet_name)
        except Exception as e:
            st.error(
                f"Error exporting Excel. Ensure dependencies are installed: `pip install xlsxwriter openpyxl`. Error: {e}")
            return None

    output.seek(0)
    return output.getvalue()


# -------------------------------
# STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="PracTrack EDU ", page_icon="🩺", layout="wide")
st.title("🩺 PracTrack EDU  — Class & Site Management")

menu = st.sidebar.radio("Navigate", [
    "🏠 Home",
    "📤 Upload Class List",
    "👩‍🎓 Manage Students",
    "⚙️ Site Requirements",
    "🕒 Log Practical Hours",
    "📋 View Records",
    "📈 Completion Summary"
])

# Display a persistent message if one is set
if st.session_state.message:
    msg_type, msg_body = st.session_state.message
    if msg_type == 'success':
        st.sidebar.success(msg_body)
    elif msg_type == 'warning':
        st.sidebar.warning(msg_body)
    elif msg_type == 'error':
        st.sidebar.error(msg_body)
    st.session_state.message = None  # Clear message after display

# -------------------------------
# HOME
# -------------------------------
if menu == "🏠 Home":
    students_df = get_students_df()
    records_df = get_records_df()
    sites_df = get_sites_df()
    st.header("Welcome — Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Students", len(students_df))
    col2.metric("Log Entries", len(records_df))
    total_hours = records_df['total_hours'].sum() if not records_df.empty else 0
    col3.metric("Total Hours Logged", f"{total_hours:.1f}")

    styled_sites_df = sites_df.copy()
    styled_sites_df['required_hours'] = styled_sites_df['required_hours'].apply(lambda x: f"{x:.1f}")
    st.table(styled_sites_df)

# -------------------------------
# UPLOAD CLASS LIST
# -------------------------------
elif menu == "📤 Upload Class List":
    st.header("Upload Class List (Excel/CSV)")
    uploaded_file = st.file_uploader("Choose file", type=["xlsx", "csv"])

    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                # Use str dtype for 'student_id' column to prevent reading it as a mix of int/str
                df_upload = pd.read_csv(uploaded_file, dtype={'student_id': str})
            else:
                df_upload = pd.read_excel(uploaded_file, dtype={'student_id': str})
        except Exception as e:
            st.error(f"Could not read file: {e}")
            df_upload = None

        if df_upload is not None:
            # Clean up column headers before display/mapping
            df_upload.columns = [str(c).strip().lower() for c in df_upload.columns]

            standard_cols = ['student_name', 'student_initials', 'student_id']
            found_cols = [c for c in df_upload.columns if c in standard_cols]

            if not all(col in found_cols for col in ['student_name', 'student_id']):
                st.warning(
                    "Dataframe headers must contain 'student_name' and 'student_id' (lowercase assumed). Please check the column headers in your file.")
                st.dataframe(df_upload.head(50))

            elif st.button("Import Students"):
                added = 0
                skipped = 0
                for _, row in df_upload.iterrows():
                    name = str(row.get('student_name', '')).strip()
                    student_id = str(row.get('student_id', '')).strip()
                    initials = str(row.get('student_initials', '')).strip() if 'student_initials' in row else ''
                    if initials == 'nan': initials = ''

                    if name and student_id:
                        success, msg = add_student(name, initials, student_id)
                        if success:
                            added += 1
                        else:
                            skipped += 1

                st.session_state.message = (
                'success', f"Added {added} students, skipped {skipped} (duplicates or empty data).")
                st.rerun()
            else:
                st.dataframe(df_upload.head(50))


# -------------------------------
# MANAGE STUDENTS
# -------------------------------
elif menu == "👩‍🎓 Manage Students":
    st.header("Manage Students")
    df = get_students_df()
    if df.empty:
        st.info("No students yet")
    else:
        # Display student list
        st.dataframe(df[['student_name', 'student_initials', 'student_id']])

        student_name_list = sorted(df['student_name'].unique().tolist())
        student_name_options = [''] + student_name_list
        selected_name = st.selectbox("Select Student Name to Manage", student_name_options,
                                     key='manage_student_name_select')

        selected_id = ''
        initial_name = ''

        if selected_name:
            try:
                selected_id = df[df['student_name'] == selected_name]['student_id'].iloc[0]
                initial_name = selected_name
            except IndexError:
                pass

        new_name = st.text_input("Edit Name (will be used to update the student's name)", value=initial_name,
                                 key='manage_student_name_input')

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Update Name",
                         key='update_name_main') and selected_id and new_name and new_name != initial_name:
                update_student(selected_id, new_name)
                st.session_state.message = ('success', f"Updated name for ID {selected_id} to {new_name}.")
                st.rerun()

        with col2:
            if st.button("Delete Student", key='delete_student_main') and selected_id:
                delete_student(selected_id)
                st.session_state.message = (
                'warning', f"Deleted student '{selected_name}' (ID: {selected_id}) and all related hours.")
                st.rerun()

        # --- Reset System Data Feature (Good for Prototyping/Demo) ---
        st.markdown("---")
        with st.expander("System Maintenance: Reset All Data"):
            st.warning("This action will permanently delete ALL student records and ALL hour logs from the database.")

            if st.button("Confirm and Reset System Data", key='reset_data_final'):
                run_query("DELETE FROM students")
                run_query("DELETE FROM hours_log")
                # Clear site requirements too for a full reset
                # Only clear default entries to avoid deleting necessary ones later
                run_query(
                    "DELETE FROM site_requirements WHERE site_name NOT IN ('Site A - Hospital A', 'Site B - Clinic B', 'Site C - Laboratory C', 'Site D - Community D')")

                st.session_state.message = ('error', "SYSTEM DATA RESET COMPLETE. Please re-upload your class list.")
                st.rerun()
        # ----------------------------------------------------


# -------------------------------
# SITE REQUIREMENTS
# -------------------------------
elif menu == "⚙️ Site Requirements":
    st.header("Site Requirements (CRUD)")
    df = get_sites_df()
    st.dataframe(df)

    action = st.radio("Select Action", ["Add New Site", "Update Existing Site", "Delete Site"])

    if action == "Add New Site":
        with st.form("add_site_form"):
            site_name = st.text_input("New Site Name", key='add_site_name')
            hours = st.number_input("Required Hours", min_value=0.0, value=0.0, key='add_site_hours')
            if st.form_submit_button("Add Site"):
                if site_name:
                    set_site_requirement(site_name, hours)
                    st.session_state.message = ('success', f"Added new site '{site_name}' with {hours} hours.")
                    st.rerun()
                else:
                    st.error("Site name cannot be empty.")

    elif action == "Update Existing Site":
        if not df.empty:
            with st.form("update_site_form"):
                site_to_update = st.selectbox("Select Site to Update", df['site_name'], key='update_site_select')

                current_hours = df[df['site_name'] == site_to_update]['required_hours'].iloc[
                    0] if site_to_update else 0.0

                new_hours = st.number_input(f"New Required Hours for '{site_to_update}'", min_value=0.0,
                                            value=current_hours, key='update_site_hours')

                if st.form_submit_button("Update Requirement"):
                    set_site_requirement(site_to_update, new_hours)
                    st.session_state.message = (
                    'success', f"Updated '{site_to_update}' requirement to {new_hours} hours.")
                    st.rerun()
        else:
            st.info("No sites to update.")


    elif action == "Delete Site":
        if not df.empty:
            with st.form("delete_site_form"):
                site_del = st.selectbox("Select site to delete", df['site_name'], key='site_del_select')
                delete_submitted = st.form_submit_button("Delete Site")

                if delete_submitted:
                    run_query("DELETE FROM site_requirements WHERE site_name=?", (site_del,))
                    st.session_state.message = ('warning', f"Deleted site '{site_del}'.")
                    st.rerun()
        else:
            st.info("No sites to delete.")

# -------------------------------
# LOG PRACTICAL HOURS
# -------------------------------
elif menu == "🕒 Log Practical Hours":
    st.header("Log Practical Hours")
    students = get_students_df()
    sites = get_sites_df()

    if students.empty:
        st.warning("No students in system. Please add students via 'Manage Students' or 'Upload Class List'.")
    elif sites.empty:
        st.warning("No sites defined. Please define sites in 'Site Requirements'.")
    else:
        with st.form("hours_log_form"):
            lecturer = st.text_input("Lecturer Name")
            student_name_list = students['student_name'].tolist()
            student_name = st.selectbox("Select Student", student_name_list)

            student_id = ''
            if student_name and not students[students['student_name'] == student_name]['student_id'].empty:
                student_id = students[students['student_name'] == student_name]['student_id'].iloc[0]

            site_list = sites['site_name'].tolist()
            site = st.selectbox("Select Site", site_list)
            date = st.date_input("Date", value=datetime.today())

            col1, col2 = st.columns(2)
            with col1:
                start_time_in = st.time_input("Start", value=time(9, 0))
            with col2:
                end_time_in = st.time_input("End", value=time(17, 0))

            total_hours = 0
            try:
                start_dt = datetime.combine(date, start_time_in)
                end_dt = datetime.combine(date, end_time_in)

                if end_dt < start_dt:
                    end_dt = end_dt + pd.Timedelta(days=1)

                duration = end_dt - start_dt
                total_hours = round(duration.total_seconds() / 3600, 2)
                st.info(f"Calculated Duration: {total_hours} hours")
            except Exception:
                st.error("Error calculating hours. Check date/time inputs.")

            notes = st.text_area("Notes")

            if st.form_submit_button("Log Hours"):
                required_fields_ok = all([
                    total_hours > 0,
                    lecturer.strip(),
                    site.strip(),
                    student_id.strip()
                ])

                if required_fields_ok:
                    add_hours_log(lecturer.strip(), student_name, student_id.strip(), site.strip(), str(date),
                                  str(start_time_in), str(end_time_in), total_hours, notes)
                    st.session_state.message = ('success', f"Logged {total_hours} hours for {student_name} at {site}.")
                    st.rerun()
                else:
                    st.error(
                        "Cannot log 0 or negative hours, or missing required fields (Lecturer/Site/Student ID). Check start/end times and ensure all fields are filled.")

# -------------------------------
# VIEW RECORDS
# -------------------------------
elif menu == "📋 View Records":
    st.header("All Records")
    df = get_records_df()
    if df.empty:
        st.info("No records yet")
    else:
        st.dataframe(df)
        excel_bytes = to_excel_bytes({"Records": df})
        if excel_bytes:
            st.download_button("Export Excel", data=excel_bytes, file_name="records.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------------
# COMPLETION SUMMARY
# -------------------------------
elif menu == "📈 Completion Summary":
    st.header("Completion Summary")
    summary = calculate_summary()
    if summary.empty:
        st.info("No data. Add students and log hours.")
    else:
        st.dataframe(summary)
        excel_bytes = to_excel_bytes({"Summary": summary})
        if excel_bytes:
            st.download_button("Export Summary", data=excel_bytes, file_name="summary.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")