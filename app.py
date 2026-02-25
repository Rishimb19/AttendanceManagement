# app.py
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
# ------------------------------
# App Initialization
# ------------------------------
app = Flask(__name__)
app.secret_key = '2485fdb6dad2ad10d3e8ae066b635f9ca94fbd2815e275eda1c2358364530d59'

DATABASE = 'database.db'

# ------------------------------
# Database helpers
# ------------------------------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def migrate_db():
    """Add new columns to students and subjects tables if they don't exist."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Check students table for parent fields
        cursor.execute("PRAGMA table_info(students)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'parent_name' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN parent_name TEXT")
        if 'parent_phone' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN parent_phone TEXT")
        if 'parent_email' not in columns:
            cursor.execute("ALTER TABLE students ADD COLUMN parent_email TEXT")

        # Subjects table migration (course, semester)
        cursor.execute("PRAGMA table_info(subjects)")
        subj_columns = [col[1] for col in cursor.fetchall()]

        if 'course' not in subj_columns:
            cursor.execute("ALTER TABLE subjects ADD COLUMN course TEXT")
            cursor.execute("UPDATE subjects SET course = 'BCom' WHERE course IS NULL")
        if 'semester' not in subj_columns:
            cursor.execute("ALTER TABLE subjects ADD COLUMN semester INTEGER")
            cursor.execute("UPDATE subjects SET semester = 1 WHERE semester IS NULL")

        # Create unique index on subjects
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_subjects_unique 
            ON subjects(name, course, semester)
        ''')

        db.commit()

def init_db():
    """Create tables if they don't exist."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Students table with parent fields
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usn TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT,
                class TEXT NOT NULL,
                department TEXT NOT NULL,
                parent_name TEXT,
                parent_phone TEXT,
                parent_email TEXT
            )
        ''')

        # Attendance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT CHECK(status IN ('Present','Absent')) NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
                UNIQUE(student_id, date)
            )
        ''')

        # Tasks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                due_date TEXT NOT NULL
            )
        ''')

        # Student-Task completion table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS student_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                status TEXT CHECK(status IN ('Pending','Completed')) NOT NULL DEFAULT 'Pending',
                completed_date TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
                UNIQUE(task_id, student_id)
            )
        ''')

        # Subjects table (with course and semester)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                course TEXT,
                semester INTEGER,
                description TEXT
            )
        ''')

        # Marks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                exam_type TEXT NOT NULL,
                marks_obtained REAL NOT NULL,
                max_marks REAL NOT NULL,
                exam_date TEXT,
                remarks TEXT,
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
            )
        ''')

        # Admin table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')

        # Insert default admin if none exists
        cursor.execute("SELECT COUNT(*) FROM admin")
        if cursor.fetchone()[0] == 0:
            hashed = generate_password_hash('admin')
            cursor.execute("INSERT INTO admin (username, password_hash) VALUES (?, ?)",
                           ('admin', hashed))

        db.commit()
        # Run migration to add new columns if needed
        migrate_db()

# ------------------------------
# Login required decorator
# ------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------
# Helper: get distinct classes/departments
# ------------------------------
def get_class_department_options():
    db = get_db()
    classes = db.execute("SELECT DISTINCT class FROM students ORDER BY class").fetchall()
    departments = db.execute("SELECT DISTINCT department FROM students ORDER BY department").fetchall()
    return [c['class'] for c in classes], [d['department'] for d in departments]

# ------------------------------
# Routes
# ------------------------------
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        admin = db.execute(
            "SELECT * FROM admin WHERE username = ?", (username,)
        ).fetchone()
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    # Get selected date from query string (default to today)
    selected_date = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))

    # Total students
    total_students = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]

    # Overall attendance stats (all-time)
    total_attendance = db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    present_count = db.execute(
        "SELECT COUNT(*) FROM attendance WHERE status = 'Present'"
    ).fetchone()[0]
    absent_count = total_attendance - present_count
    overall_percent = round((present_count / total_attendance * 100), 2) if total_attendance > 0 else 0

    # Department-wise attendance for selected date
    dept_attendance = db.execute('''
        SELECT 
            s.department,
            COUNT(s.id) as total_students,
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
            SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id AND a.date = ?
        GROUP BY s.department
        ORDER BY s.department
    ''', (selected_date,)).fetchall()

    # Recent attendance (last 5) - keep for quick view
    recent = db.execute('''
        SELECT s.name, s.class, s.department, a.date, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.date DESC, a.id DESC
        LIMIT 5
    ''').fetchall()

    return render_template('dashboard.html',
                           total_students=total_students,
                           total_attendance=total_attendance,
                           present_count=present_count,
                           absent_count=absent_count,
                           overall_percent=overall_percent,
                           dept_attendance=dept_attendance,
                           selected_date=selected_date,
                           recent=recent)

# ------------------------------
# Student Management (with parent details)
# ------------------------------
@app.route('/students')
@login_required
def students():
    db = get_db()
    students_list = db.execute('''
        SELECT * FROM students ORDER BY class, department, name
    ''').fetchall()
    classes, departments = get_class_department_options()
    return render_template('students.html', students=students_list,
                           classes=classes, departments=departments)

@app.route('/students/add', methods=['POST'])
@login_required
def add_student():
    usn = request.form['usn'].strip()
    name = request.form['name'].strip()
    email = request.form['email'].strip()
    phone = request.form['phone'].strip()
    class_ = request.form['class'].strip()
    department = request.form['department'].strip()
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    parent_email = request.form.get('parent_email', '').strip()

    if not usn or not name or not email or not class_ or not department:
        flash('USN, Name, Email, Class, and Department are required.', 'danger')
        return redirect(url_for('students'))

    db = get_db()
    try:
        db.execute(
            '''INSERT INTO students (usn, name, email, phone, class, department, parent_name, parent_phone, parent_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (usn, name, email, phone, class_, department, parent_name, parent_phone, parent_email)
        )
        db.commit()
        flash('Student added successfully.', 'success')
    except sqlite3.IntegrityError as e:
        if 'UNIQUE constraint failed' in str(e):
            flash('USN or Email already exists.', 'danger')
        else:
            flash('Error adding student.', 'danger')
    return redirect(url_for('students'))

@app.route('/students/edit/<int:id>', methods=['POST'])
@login_required
def edit_student(id):
    usn = request.form['usn'].strip()
    name = request.form['name'].strip()
    email = request.form['email'].strip()
    phone = request.form['phone'].strip()
    class_ = request.form['class'].strip()
    department = request.form['department'].strip()
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    parent_email = request.form.get('parent_email', '').strip()

    if not usn or not name or not email or not class_ or not department:
        flash('All fields except phone and parent details are required.', 'danger')
        return redirect(url_for('students'))

    db = get_db()
    existing = db.execute(
        "SELECT id FROM students WHERE (usn = ? OR email = ?) AND id != ?",
        (usn, email, id)
    ).fetchone()
    if existing:
        flash('USN or Email already in use by another student.', 'danger')
        return redirect(url_for('students'))

    db.execute(
        '''UPDATE students SET usn=?, name=?, email=?, phone=?, class=?, department=?, parent_name=?, parent_phone=?, parent_email=?
           WHERE id=?''',
        (usn, name, email, phone, class_, department, parent_name, parent_phone, parent_email, id)
    )
    db.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('students'))

@app.route('/students/delete/<int:id>', methods=['POST'])
@login_required
def delete_student(id):
    db = get_db()
    db.execute("DELETE FROM students WHERE id = ?", (id,))
    db.commit()
    flash('Student deleted successfully.', 'success')
    return redirect(url_for('students'))

# ------------------------------
# Attendance (individual and bulk)
# ------------------------------
@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    """Mark individual attendance and view history."""
    db = get_db()
    if request.method == 'POST':
        student_id = request.form['student_id']
        status = request.form['status']
        date = request.form.get('date', datetime.today().strftime('%Y-%m-%d'))
        try:
            db.execute(
                "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                (student_id, date, status)
            )
            db.commit()
            flash('Attendance marked successfully.', 'success')
        except sqlite3.IntegrityError:
            flash('Attendance for this student on this date already exists.', 'danger')
        return redirect(url_for('attendance'))

    students_list = db.execute(
        "SELECT id, usn, name, class, department FROM students ORDER BY class, department, name"
    ).fetchall()
    history = db.execute('''
        SELECT s.name, s.class, s.department, a.date, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.date DESC, a.id DESC
    ''').fetchall()
    classes, departments = get_class_department_options()
    return render_template('attendance.html',
                           students=students_list,
                           history=history,
                           today=datetime.today().strftime('%Y-%m-%d'),
                           classes=classes,
                           departments=departments)

@app.route('/attendance/bulk', methods=['GET', 'POST'])
@login_required
def bulk_attendance():
    """Mark attendance for multiple students at once with filters."""
    db = get_db()
    if request.method == 'POST':
        date = request.form['date']
        class_filter = request.form.get('class_filter')
        dept_filter = request.form.get('dept_filter')
        query = "SELECT id FROM students"
        params = []
        conditions = []
        if class_filter and class_filter != 'All':
            conditions.append("class = ?")
            params.append(class_filter)
        if dept_filter and dept_filter != 'All':
            conditions.append("department = ?")
            params.append(dept_filter)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        student_ids = [row['id'] for row in db.execute(query, params).fetchall()]

        success_count = 0
        exists_count = 0
        for sid in student_ids:
            status = request.form.get(f'status_{sid}', 'Present')
            try:
                db.execute(
                    "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)",
                    (sid, date, status)
                )
                success_count += 1
            except sqlite3.IntegrityError:
                exists_count += 1
        db.commit()
        flash(f'Bulk attendance marked: {success_count} new records, {exists_count} already existed.', 'success')
        return redirect(url_for('attendance'))

    classes, departments = get_class_department_options()
    class_filter = request.args.get('class_filter', 'All')
    dept_filter = request.args.get('dept_filter', 'All')
    query = "SELECT id, usn, name, class, department FROM students"
    params = []
    conditions = []
    if class_filter and class_filter != 'All':
        conditions.append("class = ?")
        params.append(class_filter)
    if dept_filter and dept_filter != 'All':
        conditions.append("department = ?")
        params.append(dept_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY class, department, name"
    students = db.execute(query, params).fetchall()
    return render_template('bulk_attendance.html',
                           students=students,
                           classes=classes,
                           departments=departments,
                           selected_class=class_filter,
                           selected_dept=dept_filter,
                           today=datetime.today().strftime('%Y-%m-%d'))

# ------------------------------
# Tasks Management
# ------------------------------
# ------------------------------
# Tasks Management
# ------------------------------
# ------------------------------
# Tasks Management
# ------------------------------
@app.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    db = get_db()
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form['description'].strip()
        due_date = request.form['due_date']
        
        if not title or not due_date:
            flash('Title and due date are required.', 'danger')
            return redirect(url_for('tasks'))

        cursor = db.execute(
            "INSERT INTO tasks (title, description, due_date) VALUES (?, ?, ?)",
            (title, description, due_date)
        )
        task_id = cursor.lastrowid

        assign_all = request.form.get('assign_all')
        if assign_all:
            students = db.execute("SELECT id FROM students").fetchall()
            for s in students:
                try:
                    db.execute(
                        "INSERT INTO student_tasks (task_id, student_id, status) VALUES (?, ?, 'Pending')",
                        (task_id, s['id'])
                    )
                except sqlite3.IntegrityError:
                    pass
            db.commit()
            flash('Task added and assigned to all students.', 'success')
        else:
            flash('Task added. Use "Assign" to assign to students.', 'success')
        return redirect(url_for('tasks'))

    # GET: Fetch all tasks with counts
    tasks_list = db.execute('''
        SELECT t.*,
               COUNT(DISTINCT st.id) as total_assigned,
               SUM(CASE WHEN st.status = 'Completed' THEN 1 ELSE 0 END) as completed_count
        FROM tasks t
        LEFT JOIN student_tasks st ON t.id = st.task_id
        GROUP BY t.id
        ORDER BY t.due_date
    ''').fetchall()
    
    return render_template('tasks.html', tasks=tasks_list)

@app.route('/tasks/<int:task_id>')
@login_required
def task_detail(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('tasks'))

    student_tasks = db.execute('''
        SELECT s.id as student_id, s.usn, s.name, s.class, s.department,
               st.status, st.completed_date
        FROM students s
        LEFT JOIN student_tasks st ON s.id = st.student_id AND st.task_id = ?
        ORDER BY s.class, s.department, s.name
    ''', (task_id,)).fetchall()

    return render_template('task_detail.html', task=task, student_tasks=student_tasks)

@app.route('/tasks/assign/<int:task_id>', methods=['GET'])
@login_required
def assign_task_page(task_id):
    """Display the assignment page for a task"""
    db = get_db()
    
    # Get the task first
    task = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('tasks'))
    
    # Get all students with assignment status
    all_students = db.execute("SELECT * FROM students ORDER BY class, department, name").fetchall()
    
    # Get already assigned student IDs
    assigned = db.execute(
        "SELECT student_id FROM student_tasks WHERE task_id = ?", (task_id,)
    ).fetchall()
    assigned_ids = [a['student_id'] for a in assigned]
    
    # Create a list with assignment status
    students_with_status = []
    for student in all_students:
        student_dict = dict(student)
        student_dict['assigned'] = student['id'] in assigned_ids
        students_with_status.append(student_dict)
    
    return render_template('assign_task.html', 
                         task=task, 
                         all_students=students_with_status,
                         assigned_count=len(assigned_ids),
                         total_students=len(all_students))

@app.route('/tasks/update_assignments/<int:task_id>', methods=['POST'])
@login_required
def update_task_assignments(task_id):
    """Handle both assigning and unassigning students"""
    db = get_db()
    
    # Get all student IDs from the form
    selected_student_ids = request.form.getlist('student_ids')
    selected_student_ids = [int(id) for id in selected_student_ids]
    
    # Get all students
    all_students = db.execute("SELECT id FROM students").fetchall()
    all_student_ids = [s['id'] for s in all_students]
    
    # Get currently assigned students
    currently_assigned = db.execute(
        "SELECT student_id FROM student_tasks WHERE task_id = ?", (task_id,)
    ).fetchall()
    currently_assigned_ids = [a['student_id'] for a in currently_assigned]
    
    # Students to assign (in selected but not currently assigned)
    to_assign = [sid for sid in selected_student_ids if sid not in currently_assigned_ids]
    
    # Students to unassign (currently assigned but not in selected)
    to_unassign = [sid for sid in currently_assigned_ids if sid not in selected_student_ids]
    
    # Perform assignments
    assign_count = 0
    for sid in to_assign:
        try:
            db.execute(
                "INSERT INTO student_tasks (task_id, student_id, status) VALUES (?, ?, 'Pending')",
                (task_id, sid)
            )
            assign_count += 1
        except sqlite3.IntegrityError:
            pass
    
    # Perform unassignments
    unassign_count = 0
    for sid in to_unassign:
        db.execute(
            "DELETE FROM student_tasks WHERE task_id = ? AND student_id = ?",
            (task_id, sid)
        )
        unassign_count += 1
    
    db.commit()
    
    if assign_count > 0:
        flash(f'Task assigned to {assign_count} new student(s).', 'success')
    if unassign_count > 0:
        flash(f'Task unassigned from {unassign_count} student(s).', 'info')
    if assign_count == 0 and unassign_count == 0:
        flash('No changes made to assignments.', 'info')
    
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/complete/<int:task_id>/<int:student_id>', methods=['POST'])
@login_required
def complete_task(task_id, student_id):
    db = get_db()
    today = datetime.today().strftime('%Y-%m-%d')
    db.execute(
        '''UPDATE student_tasks SET status='Completed', completed_date=?
           WHERE task_id=? AND student_id=?''',
        (today, task_id, student_id)
    )
    db.commit()
    flash('Task marked as completed.', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/reset/<int:task_id>/<int:student_id>', methods=['POST'])
@login_required
def reset_task(task_id, student_id):
    db = get_db()
    db.execute(
        '''UPDATE student_tasks SET status='Pending', completed_date=NULL
           WHERE task_id=? AND student_id=?''',
        (task_id, student_id)
    )
    db.commit()
    flash('Task status reset.', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/bulk_complete/<int:task_id>', methods=['POST'])
@login_required
def bulk_complete_task(task_id):
    db = get_db()
    today = datetime.today().strftime('%Y-%m-%d')
    db.execute('''
        UPDATE student_tasks
        SET status = 'Completed', completed_date = ?
        WHERE task_id = ? AND status = 'Pending'
    ''', (today, task_id))
    db.commit()
    flash('All pending students marked as completed.', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/assign_to_student/<int:task_id>/<int:student_id>', methods=['POST'])
@login_required
def assign_task_to_student(task_id, student_id):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO student_tasks (task_id, student_id, status) VALUES (?, ?, 'Pending')",
            (task_id, student_id)
        )
        db.commit()
        flash('Task assigned to student.', 'success')
    except sqlite3.IntegrityError:
        flash('Task already assigned to this student.', 'warning')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/tasks/delete/<int:id>', methods=['POST'])
@login_required
def delete_task(id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (id,))
    db.commit()
    flash('Task deleted.', 'success')
    return redirect(url_for('tasks'))
#---------------
# Subjects Management
# ------------------------------
@app.route('/subjects', methods=['GET', 'POST'])
@login_required
def subjects():
    db = get_db()
    if request.method == 'POST':
        name = request.form['name'].strip()
        course = request.form['course'].strip()
        semester = request.form['semester']
        description = request.form['description'].strip()

        if not name or not course or not semester:
            flash('Subject name, course, and semester are required.', 'danger')
            return redirect(url_for('subjects'))

        try:
            db.execute(
                "INSERT INTO subjects (name, course, semester, description) VALUES (?, ?, ?, ?)",
                (name, course, semester, description)
            )
            db.commit()
            flash('Subject added successfully.', 'success')
        except sqlite3.IntegrityError:
            flash('Subject with this name, course, and semester already exists.', 'danger')
        return redirect(url_for('subjects'))

    # Get filter parameters
    filter_course = request.args.get('course', '')
    filter_semester = request.args.get('semester', '')

    # Build query with optional filters
    query = "SELECT * FROM subjects"
    params = []
    conditions = []
    if filter_course:
        conditions.append("course = ?")
        params.append(filter_course)
    if filter_semester:
        conditions.append("semester = ?")
        params.append(filter_semester)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY course, semester, name"

    subjects_list = db.execute(query, params).fetchall()

    courses = ['BCom', 'BCA', 'BBA', 'BSc']
    semesters = list(range(1, 9))
    return render_template('subjects.html',
                           subjects=subjects_list,
                           courses=courses,
                           semesters=semesters,
                           filter_course=filter_course,
                           filter_semester=filter_semester)

@app.route('/subjects/edit/<int:id>', methods=['POST'])
@login_required
def edit_subject(id):
    name = request.form['name'].strip()
    course = request.form['course'].strip()
    semester = request.form['semester']
    description = request.form['description'].strip()

    if not name or not course or not semester:
        flash('Subject name, course, and semester are required.', 'danger')
        return redirect(url_for('subjects'))

    db = get_db()
    existing = db.execute(
        "SELECT id FROM subjects WHERE name = ? AND course = ? AND semester = ? AND id != ?",
        (name, course, semester, id)
    ).fetchone()
    if existing:
        flash('Subject with this name, course, and semester already exists.', 'danger')
        return redirect(url_for('subjects'))

    db.execute(
        "UPDATE subjects SET name = ?, course = ?, semester = ?, description = ? WHERE id = ?",
        (name, course, semester, description, id)
    )
    db.commit()
    flash('Subject updated successfully.', 'success')
    return redirect(url_for('subjects'))

@app.route('/subjects/delete/<int:id>', methods=['POST'])
@login_required
def delete_subject(id):
    db = get_db()
    db.execute("DELETE FROM subjects WHERE id = ?", (id,))
    db.commit()
    flash('Subject deleted.', 'success')
    return redirect(url_for('subjects'))

# ------------------------------
# Marks Management
# ------------------------------
@app.route('/marks', methods=['GET', 'POST'])
@login_required
def marks():
    db = get_db()
    if request.method == 'POST':
        student_id = request.form['student_id']
        subject_id = request.form['subject_id']
        exam_type = request.form['exam_type'].strip()
        marks_obtained = request.form['marks_obtained']
        max_marks = request.form['max_marks']
        exam_date = request.form.get('exam_date') or None
        remarks = request.form.get('remarks', '').strip()

        if not all([student_id, subject_id, exam_type, marks_obtained, max_marks]):
            flash('All fields except remarks are required.', 'danger')
            return redirect(url_for('marks'))

        try:
            db.execute(
                '''INSERT INTO marks
                   (student_id, subject_id, exam_type, marks_obtained, max_marks, exam_date, remarks)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (student_id, subject_id, exam_type, marks_obtained, max_marks, exam_date, remarks)
            )
            db.commit()
            flash('Marks added successfully.', 'success')
        except Exception as e:
            flash(f'Error adding marks: {str(e)}', 'danger')
        return redirect(url_for('marks'))

    # GET: show all marks (no filters)
    query = '''
        SELECT m.*, s.name as student_name, s.usn, sub.name as subject_name,
               sub.course, sub.semester
        FROM marks m
        JOIN students s ON m.student_id = s.id
        JOIN subjects sub ON m.subject_id = sub.id
        ORDER BY sub.course, sub.semester, m.exam_date DESC, m.id DESC
    '''
    marks_list = db.execute(query).fetchall()

    students = db.execute("SELECT id, usn, name FROM students ORDER BY name").fetchall()
    subjects = db.execute("SELECT id, name, course, semester FROM subjects ORDER BY course, semester, name").fetchall()

    return render_template('marks.html',
                           marks=marks_list,
                           students=students,
                           subjects=subjects)

@app.route('/marks/bulk', methods=['GET', 'POST'])
@login_required
def bulk_marks():
    db = get_db()
    if request.method == 'POST':
        subject_id = request.form['subject_id']
        exam_type = request.form['exam_type'].strip()
        exam_date = request.form.get('exam_date') or None
        remarks = request.form.get('remarks', '').strip()
        student_ids = request.form.getlist('student_ids')
        marks_obtained_list = request.form.getlist('marks_obtained')
        max_marks_list = request.form.getlist('max_marks')

        if not subject_id or not exam_type:
            flash('Subject and exam type are required.', 'danger')
            return redirect(url_for('bulk_marks'))

        success_count = 0
        for i, student_id in enumerate(student_ids):
            marks_obtained = marks_obtained_list[i] if i < len(marks_obtained_list) else ''
            max_marks = max_marks_list[i] if i < len(max_marks_list) else ''
            if not marks_obtained or not max_marks:
                continue
            try:
                db.execute(
                    '''INSERT INTO marks
                       (student_id, subject_id, exam_type, marks_obtained, max_marks, exam_date, remarks)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (student_id, subject_id, exam_type, marks_obtained, max_marks, exam_date, remarks)
                )
                success_count += 1
            except sqlite3.IntegrityError:
                pass
        db.commit()
        flash(f'Bulk marks added: {success_count} records inserted.', 'success')
        return redirect(url_for('marks'))

    course_filter = request.args.get('course', '')
    semester_filter = request.args.get('semester', '')
    subject_filter = request.args.get('subject_id', '')

    subjects = db.execute("SELECT id, name, course, semester FROM subjects ORDER BY course, semester, name").fetchall()
    courses = ['BCom', 'BCA', 'BBA', 'BSc']
    semesters = list(range(1, 9))

    students = []
    selected_subject = None
    if subject_filter:
        selected_subject = db.execute("SELECT * FROM subjects WHERE id = ?", (subject_filter,)).fetchone()
        if selected_subject:
            query = "SELECT id, usn, name, class, department FROM students WHERE department = ? ORDER BY name"
            students = db.execute(query, (selected_subject['course'],)).fetchall()
    elif course_filter and semester_filter:
        subjects = db.execute(
            "SELECT id, name FROM subjects WHERE course = ? AND semester = ? ORDER BY name",
            (course_filter, semester_filter)
        ).fetchall()

    return render_template('bulk_marks.html',
                           students=students,
                           subjects=subjects,
                           courses=courses,
                           semesters=semesters,
                           selected_course=course_filter,
                           selected_semester=semester_filter,
                           selected_subject_id=subject_filter,
                           selected_subject=selected_subject)

@app.route('/marks/edit/<int:id>', methods=['POST'])
@login_required
def edit_mark(id):
    student_id = request.form['student_id']
    subject_id = request.form['subject_id']
    exam_type = request.form['exam_type'].strip()
    marks_obtained = request.form['marks_obtained']
    max_marks = request.form['max_marks']
    exam_date = request.form.get('exam_date') or None
    remarks = request.form.get('remarks', '').strip()

    if not all([student_id, subject_id, exam_type, marks_obtained, max_marks]):
        flash('All fields except remarks are required.', 'danger')
        return redirect(url_for('marks'))

    db = get_db()
    db.execute(
        '''UPDATE marks SET student_id=?, subject_id=?, exam_type=?,
           marks_obtained=?, max_marks=?, exam_date=?, remarks=?
           WHERE id=?''',
        (student_id, subject_id, exam_type, marks_obtained, max_marks, exam_date, remarks, id)
    )
    db.commit()
    flash('Marks updated successfully.', 'success')
    return redirect(url_for('marks'))

@app.route('/marks/delete/<int:id>', methods=['POST'])
@login_required
def delete_mark(id):
    db = get_db()
    db.execute("DELETE FROM marks WHERE id = ?", (id,))
    db.commit()
    flash('Marks deleted.', 'success')
    return redirect(url_for('marks'))

# ------------------------------
# Individual Student Report
# ------------------------------
@app.route('/student_report/<int:student_id>')
@login_required
def student_report(student_id):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        flash('Student not found.', 'danger')
        return redirect(url_for('students'))

    attendance = db.execute('''
        SELECT
            COUNT(*) as total_days,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present_count,
            SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent_count
        FROM attendance
        WHERE student_id = ?
    ''', (student_id,)).fetchone()
    total_days = attendance['total_days'] or 0
    present = attendance['present_count'] or 0
    absent = attendance['absent_count'] or 0
    attendance_percent = round((present / total_days * 100), 2) if total_days > 0 else 0

    marks_data = db.execute('''
        SELECT sub.name as subject_name, sub.course, sub.semester,
               m.exam_type, m.marks_obtained, m.max_marks,
               m.exam_date, m.remarks
        FROM marks m
        JOIN subjects sub ON m.subject_id = sub.id
        WHERE m.student_id = ?
        ORDER BY sub.course, sub.semester, sub.name, m.exam_date
    ''', (student_id,)).fetchall()

    tasks = db.execute('''
        SELECT t.title, t.due_date, st.status, st.completed_date
        FROM student_tasks st
        JOIN tasks t ON st.task_id = t.id
        WHERE st.student_id = ?
        ORDER BY t.due_date
    ''', (student_id,)).fetchall()

    return render_template('student_report.html',
                           student=student,
                           total_days=total_days,
                           present=present,
                           absent=absent,
                           attendance_percent=attendance_percent,
                           marks=marks_data,
                           tasks=tasks)

# ------------------------------
# Reports
# ------------------------------
@app.route('/reports')
@login_required
def reports():
    db = get_db()
    class_filter = request.args.get('class_filter', 'All')
    dept_filter = request.args.get('dept_filter', 'All')

    query = '''
        SELECT s.id, s.name, s.class, s.department,
               COUNT(a.id) as total_days,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
               SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_count
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id
    '''
    params = []
    conditions = []
    if class_filter and class_filter != 'All':
        conditions.append("s.class = ?")
        params.append(class_filter)
    if dept_filter and dept_filter != 'All':
        conditions.append("s.department = ?")
        params.append(dept_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY s.id ORDER BY s.class, s.department, s.name"

    students_data = db.execute(query, params).fetchall()

    report_rows = []
    for row in students_data:
        total = row['total_days'] or 0
        present = row['present_count'] or 0
        percent = round((present / total * 100), 2) if total > 0 else 0
        report_rows.append({
            'id': row['id'],
            'name': row['name'],
            'class': row['class'],
            'department': row['department'],
            'total': total,
            'present': present,
            'absent': row['absent_count'] or 0,
            'percent': percent
        })

    classes, departments = get_class_department_options()
    return render_template('reports.html',
                           report=report_rows,
                           classes=classes,
                           departments=departments,
                           selected_class=class_filter,
                           selected_dept=dept_filter)

# ------------------------------
# API endpoints for cascading dropdowns
# ------------------------------
@app.route('/api/semesters/<department>')
@login_required
def api_semesters(department):
    """Return distinct semesters available for a given department (course)."""
    db = get_db()
    semesters = db.execute(
        "SELECT DISTINCT semester FROM subjects WHERE course = ? ORDER BY semester",
        (department,)
    ).fetchall()
    return jsonify({'semesters': [s['semester'] for s in semesters]})

@app.route('/api/subjects/<department>/<int:semester>')
@login_required
def api_subjects(department, semester):
    """Return subjects for a given department and semester."""
    db = get_db()
    subjects = db.execute(
        "SELECT id, name FROM subjects WHERE course = ? AND semester = ? ORDER BY name",
        (department, semester)
    ).fetchall()
    return jsonify({'subjects': [{'id': s['id'], 'name': s['name']} for s in subjects]})

@app.route('/api/students/<department>')
@login_required
def api_students(department):
    """Return students in a given department."""
    db = get_db()
    students = db.execute(
        "SELECT id, usn, name FROM students WHERE department = ? ORDER BY name",
        (department,)
    ).fetchall()
    return jsonify({'students': [{'id': s['id'], 'usn': s['usn'], 'name': s['name']} for s in students]})

# ------------------------------
# Run the app
# ------------------------------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)