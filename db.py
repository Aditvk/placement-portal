import os
import sqlite3
from datetime import datetime

DATABASE_FILE = 'placement.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(force=False):
    db_exists = os.path.exists(DATABASE_FILE)
    if db_exists and not force:
        return
    
    print("Initializing database...")
    conn = get_db_connection()
    
    # Read schema.sql
    with open('schema.sql', 'r') as f:
        schema = f.read()
    conn.executescript(schema)
    
    # Read seed.sql if it exists
    if os.path.exists('seed.sql'):
        with open('seed.sql', 'r') as f:
            seed = f.read()
        try:
            conn.executescript(seed)
            print("Database seeded successfully.")
        except Exception as e:
            print(f"Error seeding database: {e}")
            
    conn.commit()
    conn.close()

# Company Helpers
def get_or_create_company(name, location=None, industry_focus=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Clean company name
    name_clean = name.strip()
    
    cursor.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (name_clean,))
    row = cursor.fetchone()
    if row:
        company_id = row['id']
    else:
        cursor.execute(
            "INSERT INTO companies (name, location, industry_focus) VALUES (?, ?, ?)",
            (name_clean, location or 'Remote', industry_focus or 'Technology')
        )
        conn.commit()
        company_id = cursor.lastrowid
        
    conn.close()
    return company_id

def get_all_companies():
    conn = get_db_connection()
    companies = conn.execute("SELECT * FROM companies ORDER BY name ASC").fetchall()
    conn.close()
    return companies

# Application Helpers
def get_all_applications():
    conn = get_db_connection()
    # Join with companies to get company name and details
    query = """
        SELECT a.*, c.name as company_name, c.location as company_location, c.industry_focus 
        FROM applications a
        JOIN companies c ON a.company_id = c.id
        ORDER BY a.deadline_date ASC
    """
    apps = conn.execute(query).fetchall()
    conn.close()
    return apps

def get_application_by_id(app_id):
    conn = get_db_connection()
    query = """
        SELECT a.*, c.name as company_name, c.location as company_location, c.industry_focus 
        FROM applications a
        JOIN companies c ON a.company_id = c.id
        WHERE a.id = ?
    """
    app = conn.execute(query, (app_id,)).fetchone()
    conn.close()
    return app

def create_application(company_name, role_title, status, deadline_date, application_link, jd_match_score=0.0):
    company_id = get_or_create_company(company_name)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO applications (company_id, role_title, status, deadline_date, jd_match_score, application_link)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (company_id, role_title, status, deadline_date, jd_match_score, application_link)
    )
    conn.commit()
    app_id = cursor.lastrowid
    conn.close()
    return app_id

def update_application(app_id, company_name, role_title, status, deadline_date, application_link, jd_match_score=None):
    company_id = get_or_create_company(company_name)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if jd_match_score is not None:
        cursor.execute(
            """UPDATE applications 
               SET company_id = ?, role_title = ?, status = ?, deadline_date = ?, application_link = ?, jd_match_score = ?
               WHERE id = ?""",
            (company_id, role_title, status, deadline_date, application_link, jd_match_score, app_id)
        )
    else:
        cursor.execute(
            """UPDATE applications 
               SET company_id = ?, role_title = ?, status = ?, deadline_date = ?, application_link = ?
               WHERE id = ?""",
            (company_id, role_title, status, deadline_date, application_link, app_id)
        )
    conn.commit()
    conn.close()

def delete_application(app_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

# Interview Round Helpers
def get_interviews_for_application(app_id):
    conn = get_db_connection()
    rounds = conn.execute(
        "SELECT * FROM interview_rounds WHERE application_id = ? ORDER BY round_number ASC",
        (app_id,)
    ).fetchall()
    conn.close()
    return rounds

def get_all_interviews():
    conn = get_db_connection()
    query = """
        SELECT r.*, a.role_title, c.name as company_name 
        FROM interview_rounds r
        JOIN applications a ON r.application_id = a.id
        JOIN companies c ON a.company_id = c.id
        ORDER BY r.scheduled_time ASC
    """
    rounds = conn.execute(query).fetchall()
    conn.close()
    return rounds

def add_interview_round(application_id, round_number, round_type, scheduled_time, notes):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO interview_rounds (application_id, round_number, round_type, scheduled_time, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (application_id, round_number, round_type, scheduled_time, notes)
    )
    conn.commit()
    round_id = cursor.lastrowid
    conn.close()
    return round_id

def delete_interview_round(round_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM interview_rounds WHERE id = ?", (round_id,))
    conn.commit()
    conn.close()

def get_latest_round_badge(app_id):
    # Find the latest round by round_number for this application
    conn = get_db_connection()
    row = conn.execute(
        "SELECT round_type FROM interview_rounds WHERE application_id = ? ORDER BY round_number DESC LIMIT 1",
        (app_id,)
    ).fetchone()
    conn.close()
    return row['round_type'] if row else None

# Aggregate Stats Helper
def get_dashboard_stats():
    conn = get_db_connection()
    
    # 1. Total active applications (all applications, or we can filter out rejected/completed if we want, but total applications is standard)
    total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    
    # 2. Active interviews (scheduled in the future or count of unique applications with upcoming interview rounds)
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    active_interviews = conn.execute(
        "SELECT COUNT(DISTINCT application_id) FROM interview_rounds WHERE scheduled_time >= ?",
        (now_str,)
    ).fetchone()[0]
    
    # 3. Upcoming deadlines within 48 hours
    # In SQLite, we can check applications with deadlines between now and 48 hours from now
    # Since sqlite datetime comparison works lexicographically on ISO8601 strings:
    # We can compute the 48h limit in Python and pass it as a parameter!
    conn.close()
    return {
        'total_apps': total_apps,
        'active_interviews': active_interviews
    }
