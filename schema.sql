-- 1. Create Companies Table
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    location TEXT,
    industry_focus TEXT
);

-- 2. Create Applications Table
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    role_title TEXT NOT NULL,
    status TEXT DEFAULT 'Applied',
    deadline_date DATETIME,
    jd_match_score REAL DEFAULT 0.0,
    application_link TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

-- 3. Create Interview Rounds Table
CREATE TABLE IF NOT EXISTS interview_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    round_type TEXT,
    scheduled_time DATETIME,
    notes TEXT,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);
