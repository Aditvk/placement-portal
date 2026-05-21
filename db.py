import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

# Check if we are running in Postgres production
DATABASE_URL = os.environ.get('DATABASE_URL')
IS_POSTGRES = DATABASE_URL is not None

if IS_POSTGRES:
    import pg8000
    import pg8000.dbapi
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DATABASE_FILE = 'placement.db'

class DBRow:
    """A driver-agnostic row wrapper that supports access both by column index and column name."""
    def __init__(self, colnames, values):
        self.colnames = colnames
        self.values = list(values)
        self.row_dict = {col: val for col, val in zip(colnames, values)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.values[key]
        return self.row_dict[key]

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def keys(self):
        return self.colnames

class DBCursor:
    def __init__(self, cursor, is_postgres=False):
        self.cursor = cursor
        self.is_postgres = is_postgres

    def execute(self, query, params=()):
        if self.is_postgres:
            # Translate SQLite placeholders (?) to PostgreSQL (%s)
            query = query.replace('?', '%s')
            # Translate SQLite INSERT OR IGNORE to PostgreSQL standard
            query = query.replace('INSERT OR IGNORE', 'INSERT')
        self.cursor.execute(query, params)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        if self.is_postgres:
            colnames = [desc[0] for desc in self.cursor.description]
            return DBRow(colnames, row)
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.is_postgres:
            colnames = [desc[0] for desc in self.cursor.description]
            return [DBRow(colnames, r) for r in rows]
        return rows

    @property
    def lastrowid(self):
        if self.is_postgres:
            try:
                # In PostgreSQL, get the last generated value of sequence in current session
                self.cursor.execute("SELECT lastval();")
                val = self.cursor.fetchone()[0]
                return val
            except Exception:
                return None
        else:
            return self.cursor.lastrowid

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row

class DBConnection:
    def __init__(self, conn, is_postgres=False):
        self.conn = conn
        self.is_postgres = is_postgres

    def execute(self, query, params=()):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

    def executescript(self, script_content):
        cursor = self.cursor()
        if self.is_postgres:
            # Translate Schema/Seed scripts from SQLite to PG
            script_content = script_content.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            script_content = script_content.replace("REAL DEFAULT 0.0", "DOUBLE PRECISION DEFAULT 0.0")
            script_content = script_content.replace("DATETIME", "TIMESTAMP")
            script_content = script_content.replace("datetime", "TIMESTAMP")
            script_content = script_content.replace("INSERT OR IGNORE", "INSERT")
            cursor.execute(script_content)
        else:
            self.conn.executescript(script_content)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def cursor(self):
        if self.is_postgres:
            return DBCursor(self.conn.cursor(), is_postgres=True)
        else:
            return DBCursor(self.conn.cursor(), is_postgres=False)

def get_db_connection():
    if IS_POSTGRES:
        # Parse connection string for pg8000
        parsed = urlparse(DATABASE_URL)
        username = parsed.username
        password = parsed.password
        database = parsed.path[1:]
        hostname = parsed.hostname
        port = parsed.port or 5432
        
        raw_conn = pg8000.dbapi.connect(
            user=username,
            password=password,
            host=hostname,
            port=port,
            database=database
        )
        return DBConnection(raw_conn, is_postgres=True)
    else:
        raw_conn = sqlite3.connect(DATABASE_FILE)
        raw_conn.row_factory = sqlite3.Row
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        return DBConnection(raw_conn, is_postgres=False)

def init_db(force=False):
    db_exists = False
    if IS_POSTGRES:
        conn = get_db_connection()
        try:
            # Check if applications table exists safely using information_schema
            cursor = conn.cursor()
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_name = 'applications'
                );
            """)
            db_exists = cursor.fetchone()[0]
        except Exception as e:
            print(f"Error checking database tables: {e}")
            db_exists = False
        finally:
            conn.close()
    else:
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
    
    total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    active_interviews = conn.execute(
        "SELECT COUNT(DISTINCT application_id) FROM interview_rounds WHERE scheduled_time >= ?",
        (now_str,)
    ).fetchone()[0]
    
    conn.close()
    return {
        'total_apps': total_apps,
        'active_interviews': active_interviews
    }
