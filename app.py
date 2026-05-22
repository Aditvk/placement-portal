import os
import threading
import time
import json
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, g
import google.generativeai as genai
from dotenv import load_dotenv
import colorama
from colorama import Fore, Style
import pypdf
from pdf_generator import generate_resume_pdf

# Initialize colorama
colorama.init(autoreset=True)

# Load environment variables FIRST before importing db
load_dotenv()

import db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "neo-brutalist-secret-key-1928")

def get_db():
    if 'db_conn' not in g:
        g.db_conn = db.get_db_connection()
    return g.db_conn

@app.teardown_appcontext
def close_db(e=None):
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        db_conn.close()

# Register context processor to make db_type available in templates
@app.context_processor
def inject_db_type():
    return {
        'db_type': 'PostgreSQL (Cloud)' if db.IS_POSTGRES else 'SQLite (Local)'
    }

# Ensure database is initialized
db.init_db()

def parse_db_datetime(val):
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    if not val:
        return None
    if not isinstance(val, str):
        try:
            val = str(val)
        except Exception:
            return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    return None

# Global list for background alerts
ACTIVE_ALERTS = []

def run_deadline_checker():
    """Background thread that runs every 60 seconds and scans for application deadlines and scheduled interviews in the next 48 hours."""
    print("Background deadline checker thread started...")
    while True:
        try:
            alerts = []
            conn = db.get_db_connection()
            cursor = conn.cursor()
            
            # Fetch active applications (excluding Rejected and Offers completed)
            cursor.execute("""
                SELECT a.id, a.role_title, a.deadline_date, c.name as company_name 
                FROM applications a
                JOIN companies c ON a.company_id = c.id
                WHERE a.status != 'Rejected' AND a.status != 'Offer'
            """)
            apps = cursor.fetchall()
            
            # Fetch scheduled interview rounds
            cursor.execute("""
                SELECT r.id, r.round_type, r.scheduled_time, a.role_title, c.name as company_name
                FROM interview_rounds r
                JOIN applications a ON r.application_id = a.id
                JOIN companies c ON a.company_id = c.id
                WHERE a.status != 'Rejected'
            """)
            rounds = cursor.fetchall()
            conn.close()
            
            now = datetime.now()
            limit_48h = now + timedelta(hours=48)
            
            # Check applications
            for app_row in apps:
                deadline_str = app_row['deadline_date']
                if deadline_str:
                    deadline = parse_db_datetime(deadline_str)
                    if not deadline:
                        continue
                            
                    if now <= deadline <= limit_48h:
                        diff = deadline - now
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)
                        alerts.append({
                            'id': f"app-{app_row['id']}",
                            'type': 'Application Deadline',
                            'company': app_row['company_name'],
                            'item': f"Submit application for {app_row['role_title']}",
                            'time': deadline_str,
                            'time_remaining': f"{hours}h {minutes}m",
                            'hours_left': hours,
                            'urgency': 'high' if hours < 24 else 'medium'
                        })
            
            # Check interview rounds
            for rnd_row in rounds:
                sched_str = rnd_row['scheduled_time']
                if sched_str:
                    sched_time = parse_db_datetime(sched_str)
                    if not sched_time:
                        continue
                            
                    if now <= sched_time <= limit_48h:
                        diff = sched_time - now
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)
                        alerts.append({
                            'id': f"round-{rnd_row['id']}",
                            'type': 'Interview Round',
                            'company': rnd_row['company_name'],
                            'item': f"{rnd_row['round_type']} for {rnd_row['role_title']}",
                            'time': sched_str,
                            'time_remaining': f"{hours}h {minutes}m",
                            'hours_left': hours,
                            'urgency': 'high' if hours < 24 else 'medium'
                        })
            
            # Sort by remaining hours
            alerts.sort(key=lambda x: x['hours_left'])
            
            global ACTIVE_ALERTS
            ACTIVE_ALERTS = alerts
            
            # Console Logging (Bold Neo-Brutalist ASCII alerts)
            if alerts:
                print(f"\n{Fore.RED}{Style.BRIGHT}+----------------------------------------------------------+")
                print(f"{Fore.RED}{Style.BRIGHT}|               !!! DEADLINE WARNING (48H) !!!             |")
                print(f"{Fore.RED}{Style.BRIGHT}+----------------------------------------------------------+")
                for alert in alerts:
                    urgency_indicator = "[CRITICAL]" if alert['urgency'] == 'high' else "[UPCOMING]"
                    print(f"{Fore.RED}{Style.BRIGHT}| {urgency_indicator} {alert['type']} - {alert['company']}")
                    print(f"| Details: {alert['item']}")
                    print(f"| Due/Scheduled: {alert['time']}")
                    print(f"| Time Remaining: {Fore.YELLOW}{alert['time_remaining']} left")
                    print(f"{Fore.RED}{Style.BRIGHT}+----------------------------------------------------------+")
                print()
                
        except Exception as e:
            print(f"Error in background scheduler thread: {e}")
            
        time.sleep(60)

# Start background thread
checker_thread = threading.Thread(target=run_deadline_checker, daemon=True)
checker_thread.start()

# Context processor to inject background alerts into all templates
@app.context_processor
def inject_alerts():
    return dict(active_alerts=ACTIVE_ALERTS)

# Routing Logic
@app.route('/')
def dashboard():
    # 0. Get single request-scoped database connection
    conn = get_db()

    # 1. Fetch dashboard statistics and applications using the shared connection
    stats = db.get_dashboard_stats(conn=conn)
    apps = db.get_all_applications(conn=conn)
    
    # 2. Bulk fetch all raw interview rounds using the shared connection
    all_rounds = db.get_all_interview_rounds(conn=conn)
    
    # Map application_id to its latest round type using Python in-memory grouping
    latest_rounds = {}
    for r in all_rounds:
        app_id = r['application_id']
        r_num = r['round_number']
        r_type = r['round_type']
        if app_id not in latest_rounds or r_num > latest_rounds[app_id]['round_number']:
            latest_rounds[app_id] = {'round_number': r_num, 'round_type': r_type}

    # Enrich apps with latest round info
    enriched_apps = []
    for app_row in apps:
        app_dict = dict(app_row)
        badge_info = latest_rounds.get(app_row['id'])
        app_dict['latest_round'] = badge_info['round_type'] if badge_info else 'Applied'
        enriched_apps.append(app_dict)
    
    # 3. Get upcoming chronological items for the "Action Required" Widget
    upcoming_items = []
    
    # Applications
    for app_row in apps:
        if app_row['deadline_date'] and app_row['status'] not in ['Rejected', 'Offer']:
            upcoming_items.append({
                'title': f"{app_row['company_name']} Application",
                'subtitle': f"Submit for {app_row['role_title']}",
                'date_str': app_row['deadline_date'],
                'type': 'deadline',
                'badge': 'Deadline'
            })
            
    # Interview rounds (uses shared connection)
    rounds = db.get_all_interviews(conn=conn)
    for rnd in rounds:
        upcoming_items.append({
            'title': f"{rnd['company_name']} Round {rnd['round_number']}",
            'subtitle': f"{rnd['round_type']} - {rnd['role_title']}",
            'date_str': rnd['scheduled_time'],
            'type': 'interview',
            'badge': rnd['round_type']
        })
        
    # Sort items chronologically
    def parse_time(item):
        dt = parse_db_datetime(item['date_str'])
        return dt if dt else datetime.max
        
    upcoming_items = [i for i in upcoming_items if parse_time(i) >= datetime.now()]
    upcoming_items.sort(key=parse_time)
    upcoming_items = upcoming_items[:5] # limit to 5
    
    # Offers count: count applications with status = 'Offer'
    offers_count = sum(1 for a in apps if a['status'] == 'Offer')
    
    return render_template(
        'dashboard.html',
        stats=stats,
        offers_count=offers_count,
        applications=enriched_apps,
        upcoming_items=upcoming_items
    )

@app.route('/applications')
def applications_list():
    conn = get_db()
    apps = db.get_all_applications(conn=conn)
    companies = db.get_all_companies(conn=conn)
    
    # Bulk fetch all raw interview rounds using the shared connection
    all_rounds = db.get_all_interview_rounds(conn=conn)
    
    # Group the interview rounds by application_id in memory
    rounds_by_app = {}
    for r in all_rounds:
        app_id = r['application_id']
        if app_id not in rounds_by_app:
            rounds_by_app[app_id] = []
        rounds_by_app[app_id].append(dict(r))
    
    # Enrich applications with their interview rounds
    enriched_apps = []
    for app_row in apps:
        app_dict = dict(app_row)
        app_dict['rounds'] = rounds_by_app.get(app_row['id'], [])
        enriched_apps.append(app_dict)
        
    return render_template('applications.html', applications=enriched_apps, companies=companies)

@app.route('/applications/add', methods=['POST'])
def add_application():
    company_name = request.form.get('company_name')
    role_title = request.form.get('role_title')
    status = request.form.get('status', 'Applied')
    deadline_date = request.form.get('deadline_date')
    application_link = request.form.get('application_link')
    
    # Support datetime picker from HTML (which usually uses T format, e.g. 2026-05-22T23:59)
    if deadline_date and 'T' in deadline_date:
        deadline_date = deadline_date.replace('T', ' ') + ":00"
        
    if company_name and role_title:
        db.create_application(company_name, role_title, status, deadline_date, application_link)
        flash(f"Application for {company_name} successfully added!", "success")
    else:
        flash("Company name and Role title are required fields.", "error")
        
    return redirect(url_for('applications_list'))

@app.route('/applications/edit/<int:app_id>', methods=['POST'])
def edit_application(app_id):
    company_name = request.form.get('company_name')
    role_title = request.form.get('role_title')
    status = request.form.get('status', 'Applied')
    deadline_date = request.form.get('deadline_date')
    application_link = request.form.get('application_link')
    
    if deadline_date and 'T' in deadline_date:
        deadline_date = deadline_date.replace('T', ' ')
        if len(deadline_date) == 16: # No seconds
            deadline_date += ":00"
            
    if company_name and role_title:
        db.update_application(app_id, company_name, role_title, status, deadline_date, application_link)
        flash("Application successfully updated!", "success")
    else:
        flash("Company name and Role title are required.", "error")
        
    return redirect(url_for('applications_list'))

@app.route('/applications/delete/<int:app_id>', methods=['POST'])
def delete_application(app_id):
    db.delete_application(app_id)
    flash("Application deleted.", "success")
    return redirect(url_for('applications_list'))

@app.route('/applications/<int:app_id>/rounds/add', methods=['POST'])
def add_interview_round(app_id):
    round_number = request.form.get('round_number', type=int)
    round_type = request.form.get('round_type')
    scheduled_time = request.form.get('scheduled_time')
    notes = request.form.get('notes', '')
    
    if scheduled_time and 'T' in scheduled_time:
        scheduled_time = scheduled_time.replace('T', ' ')
        if len(scheduled_time) == 16:
            scheduled_time += ":00"
            
    if round_number and round_type:
        db.add_interview_round(app_id, round_number, round_type, scheduled_time, notes)
        flash("Interview round added!", "success")
    else:
        flash("Round number and round type are required.", "error")
        
    return redirect(url_for('applications_list'))

@app.route('/applications/<int:app_id>/rounds/delete/<int:round_id>', methods=['POST'])
def delete_interview_round(app_id, round_id):
    db.delete_interview_round(round_id)
    flash("Interview round removed.", "success")
    return redirect(url_for('applications_list'))

@app.route('/deadlines')
def deadlines_timeline():
    apps = db.get_all_applications()
    
    # Filter and sort apps that have deadlines in the future or past
    deadline_items = []
    for app_row in apps:
        if app_row['deadline_date']:
            date_str = app_row['deadline_date']
            is_upcoming = False
            hours_left = 9999
            
            dt = parse_db_datetime(date_str)
            if dt:
                if dt >= datetime.now():
                    is_upcoming = True
                    diff = dt - datetime.now()
                    hours_left = diff.total_seconds() / 3600.0
            
            deadline_items.append({
                'app_id': app_row['id'],
                'company': app_row['company_name'],
                'role': app_row['role_title'],
                'deadline': date_str,
                'is_upcoming': is_upcoming,
                'hours_left': hours_left,
                'status': app_row['status']
            })
            
    # Sort: upcoming first (closest deadline first), then past deadlines
    deadline_items.sort(key=lambda x: (not x['is_upcoming'], x['hours_left']))
    return render_template('deadlines.html', deadlines=deadline_items)

# Gemini Job Description Analyzer
@app.route('/analyzer', methods=['GET', 'POST'])
def analyzer():
    cached_resume = ""
    resume_path = 'resume.txt'
    
    # Load cached default resume if it exists
    if os.path.exists(resume_path):
        with open(resume_path, 'r', encoding='utf-8') as f:
            cached_resume = f.read()
            
    if request.method == 'GET':
        api_configured = bool(os.environ.get("GEMINI_API_KEY") or session.get("GEMINI_API_KEY"))
        apps = db.get_all_applications()
        return render_template('analyzer.html', resume=cached_resume, result=None, api_configured=api_configured, applications=apps, linked_app_id="")
        
    # POST Request - Analyze
    resume_text = request.form.get('resume', '').strip()
    jd_text = request.form.get('job_description', '').strip()
    save_resume = request.form.get('save_resume')
    user_api_key = request.form.get('api_key', '').strip()
    app_id = request.form.get('application_id', '') # Option to associate match score with a job in our DB!
    
    # Save default resume if requested
    if save_resume == 'on' and resume_text:
        with open(resume_path, 'w', encoding='utf-8') as f:
            f.write(resume_text)
        cached_resume = resume_text
        
    # API key selection: ENV or session or form input
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and user_api_key:
        api_key = user_api_key
        session['GEMINI_API_KEY'] = user_api_key
    elif not api_key:
        api_key = session.get("GEMINI_API_KEY")
        
    api_configured = bool(api_key)
    
    if not api_configured:
        flash("Gemini API Key is required to run the analysis.", "error")
        apps = db.get_all_applications()
        return render_template('analyzer.html', resume=resume_text, job_description=jd_text, result=None, api_configured=False, applications=apps, linked_app_id=app_id)
        
    if not resume_text or not jd_text:
        flash("Both Resume and Job Description are required for comparison.", "error")
        apps = db.get_all_applications()
        return render_template('analyzer.html', resume=resume_text, job_description=jd_text, result=None, api_configured=True, applications=apps, linked_app_id=app_id)
        
    try:
        # Configure Gemini API client
        genai.configure(api_key=api_key)
        
        # Build prompt
        prompt = f"""
        You are a highly selective, brutalist career advisor AI. 
        Perform a comparative analysis of the following candidate's Resume against the provided Job Description (JD).
        
        Resume Content:
        \"\"\"{resume_text}\"\"\"
        
        Job Description Content:
        \"\"\"{jd_text}\"\"\"
        
        Generate a brutalist analysis in valid JSON format. Follow this JSON schema exactly:
        {{
          "match_score": <integer from 0 to 100 representing job matching percentage>,
          "matching_keywords": [<list of up to 10 matching skills, technologies, or keywords present in both>],
          "missing_keywords": [<list of up to 10 crucial keywords, technologies, or skills requested in the JD but not shown or weak in the resume>],
          "recommendations": [<list of 3 to 5 precise, highly actionable resume update recommendations to better target this job>]
        }}
        
        Provide ONLY valid JSON. Do not wrap the JSON in markdown code blocks or add any other text.
        """
        
        model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.0})
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean markdown code blocks if the model returned them
        if response_text.startswith("```"):
            # Strip first line and last line
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()
            
        result_json = json.loads(response_text)
        
        # Auto-detect matching job tracker application if not explicitly associated
        auto_associated = False
        if not app_id and jd_text:
            apps_list = db.get_all_applications()
            for app_row in apps_list:
                co_name = app_row['company_name'].lower().strip()
                if len(co_name) >= 2 and co_name in jd_text.lower():
                    app_id = str(app_row['id'])
                    auto_associated = True
                    break

        # Optionally associate and update matching score in DB
        if app_id:
            try:
                app_int_id = int(app_id)
                app_data = db.get_application_by_id(app_int_id)
                if app_data:
                    db.update_application(
                        app_id=app_int_id,
                        company_name=app_data['company_name'],
                        role_title=app_data['role_title'],
                        status=app_data['status'],
                        deadline_date=app_data['deadline_date'],
                        application_link=app_data['application_link'],
                        jd_match_score=float(result_json.get('match_score', 0))
                    )
                    if auto_associated:
                        flash(f"Auto-associated and updated {app_data['company_name']} match score to {result_json['match_score']}%!", "success")
                    else:
                        flash(f"Updated {app_data['company_name']} match score to {result_json['match_score']}%!", "success")
            except Exception as e:
                print(f"Error updating JD match score in DB: {e}")
                
        # Fetch applications for linking dropdown
        apps = db.get_all_applications()
        return render_template(
            'analyzer.html', 
            resume=resume_text, 
            job_description=jd_text, 
            result=result_json, 
            api_configured=True,
            applications=apps,
            linked_app_id=app_id
        )
        
    except Exception as e:
        flash(f"Gemini API analysis failed: {str(e)}", "error")
        apps = db.get_all_applications()
        return render_template('analyzer.html', resume=resume_text, job_description=jd_text, result=None, api_configured=True, applications=apps, linked_app_id=app_id)

@app.route('/settings/clear_key', methods=['POST'])
def clear_api_key():
    session.pop('GEMINI_API_KEY', None)
    flash("API Key removed from browser session.", "success")
    return redirect(url_for('analyzer'))

# --- RESUME BUILDER ROUTES ---

@app.route('/resume', methods=['GET'])
def resume():
    resume_path = 'resume.txt'
    latex_path = 'resume_latex.tex'
    pdf_path = 'resume_pdf.pdf'
    
    resume_text = ""
    if os.path.exists(resume_path):
        with open(resume_path, 'r', encoding='utf-8') as f:
            resume_text = f.read()
            
    latex_code = ""
    if os.path.exists(latex_path):
        with open(latex_path, 'r', encoding='utf-8') as f:
            latex_code = f.read()
            
    compiled = os.path.exists(pdf_path)
    
    return render_template(
        'resume.html',
        resume_text=resume_text,
        latex_code=latex_code,
        compiled=compiled
    )

@app.route('/resume/import', methods=['POST'])
def import_resume():
    file = request.files.get('resume_file')
    if not file or file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for('resume'))
        
    filename = file.filename.lower()
    extracted_text = ""
    
    try:
        if filename.endswith('.txt'):
            extracted_text = file.read().decode('utf-8', errors='ignore')
        elif filename.endswith('.pdf'):
            reader = pypdf.PdfReader(file)
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            extracted_text = "\n".join(text_parts).strip()
        else:
            flash("Unsupported file format. Please upload .pdf or .txt", "error")
            return redirect(url_for('resume'))
            
        if not extracted_text:
            flash("Could not extract any text from the file.", "error")
            return redirect(url_for('resume'))
            
        with open('resume.txt', 'w', encoding='utf-8') as f:
            f.write(extracted_text)
            
        flash("Resume file parsed and imported successfully!", "success")
    except Exception as e:
        flash(f"Error importing resume: {str(e)}", "error")
        
    return redirect(url_for('resume'))

@app.route('/resume/compile', methods=['POST'])
def compile_resume():
    resume_text = request.form.get('resume_text', '').strip()
    save_as_matcher = request.form.get('save_as_matcher')
    
    if not resume_text:
        flash("Resume text cannot be empty.", "error")
        return redirect(url_for('resume'))
        
    api_key = os.environ.get("GEMINI_API_KEY") or session.get("GEMINI_API_KEY")
    if not api_key:
        flash("Gemini API Key is required to compile. Configure it on the Gemini Analyzer page first.", "error")
        return redirect(url_for('resume'))
        
    try:
        with open('resume.txt', 'w', encoding='utf-8') as f:
            f.write(resume_text)
            
        genai.configure(api_key=api_key)
        
        prompt = f"""
        You are a highly selective, Harvard-standard recruitment compiler AI.
        Analyze the following plain text resume:
        
        \"\"\"
        {resume_text}
        \"\"\"
        
        Generate:
        1. A clean, beautiful LaTeX code string for this resume. Use standard packages (article, geometry, hyperref, enumitem). Make sure all special characters (e.g. %, &, $, _, #) are correctly escaped, particularly in links or email text!
        2. A structured JSON representation matching this exact schema:
           {{
             "name": "Full Name",
             "contact": {{
               "email": "email@example.com",
               "phone": "phone number",
               "location": "City, State/Country",
               "linkedin": "linkedin slug or url",
               "github": "github slug or url"
             }},
             "summary": "Professional summary...",
             "experience": [
               {{
                 "company": "Company Name",
                 "role": "Role Title",
                 "dates": "Dates",
                 "location": "City, State",
                 "bullets": [
                   "Action bullet 1",
                   "Action bullet 2"
                 ]
               }}
             ],
             "projects": [
               {{
                 "name": "Project Name",
                 "tech_stack": "Project Stack (e.g., Python, Flask)",
                 "dates": "Dates",
                 "bullets": [
                   "Action detail 1",
                   "Action detail 2"
                 ]
               }}
             ],
             "education": [
               {{
                 "institution": "Institution Name",
                 "degree": "Degree and Major",
                 "dates": "Graduation Date",
                 "location": "City, State",
                 "gpa": "GPA (e.g., 3.8/4.0) or null"
               }}
             ],
             "skills": {{
               "Languages": ["Python", "SQL"],
               "Tools/Technologies": ["Flask", "Git"]
             }}
           }}

        Your output must be in valid JSON matching this schema:
        {{
          "latex": "<escaped LaTeX string>",
          "structured_data": <structured JSON data as shown above>
        }}

        Provide ONLY valid JSON. Do not wrap the JSON in markdown code blocks or add any other text.
        """
        
        model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.0})
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()
            
        result_json = json.loads(response_text)
        
        latex_code = result_json.get('latex', '')
        structured_data = result_json.get('structured_data', {})
        
        with open('resume_latex.tex', 'w', encoding='utf-8') as f:
            f.write(latex_code)
            
        generate_resume_pdf(structured_data, 'resume_pdf.pdf')
        
        flash("Resume successfully compiled to LaTeX and professional Harvard-standard PDF!", "success")
        
    except Exception as e:
        flash(f"Gemini compiler failed: {str(e)}", "error")
        
    return redirect(url_for('resume'))

@app.route('/resume/download/pdf', methods=['GET'])
def download_pdf():
    pdf_path = 'resume_pdf.pdf'
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True, download_name='resume.pdf')
    flash("No compiled PDF found. Please compile your resume first.", "error")
    return redirect(url_for('resume'))

@app.route('/resume/download/tex', methods=['GET'])
def download_tex():
    tex_path = 'resume_latex.tex'
    if os.path.exists(tex_path):
        return send_file(tex_path, as_attachment=True, download_name='resume.tex')
    flash("No compiled LaTeX found. Please compile your resume first.", "error")
    return redirect(url_for('resume'))

# --- FAST REGISTER ROUTES ---

@app.route('/fast-register', methods=['GET'])
def fast_register():
    parsed_data = session.get('parsed_data')
    email_text = session.get('parsed_email_text', '')
    
    matching_app = None
    if parsed_data:
        co_name = parsed_data.get('company_name', '').strip()
        role_title = parsed_data.get('role_title', '').strip()
        if co_name and role_title:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.id, a.role_title, c.name as company_name 
                FROM applications a
                JOIN companies c ON a.company_id = c.id
                WHERE LOWER(c.name) = LOWER(?) AND LOWER(a.role_title) = LOWER(?)
                LIMIT 1
            """, (co_name, role_title))
            row = cursor.fetchone()
            if row:
                matching_app = {
                    'id': row['id'],
                    'company_name': row['company_name'],
                    'role_title': row['role_title']
                }
            conn.close()
            
    return render_template(
        'fast_register.html',
        parsed_data=parsed_data,
        email_text=email_text,
        matching_app=matching_app
    )

@app.route('/fast-register/parse', methods=['POST'])
def fast_register_parse():
    email_text = request.form.get('email_text', '').strip()
    screenshot_file = request.files.get('email_screenshot')
    
    api_key = os.environ.get("GEMINI_API_KEY") or session.get("GEMINI_API_KEY")
    if not api_key:
        flash("Gemini API Key is required to parse emails. Configure it on the Gemini Analyzer page.", "error")
        return redirect(url_for('fast_register'))
        
    if not email_text and (not screenshot_file or screenshot_file.filename == ''):
        flash("Please upload an email screenshot OR paste email text.", "error")
        return redirect(url_for('fast_register'))
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.0})
        
        prompt = """
        You are a career portal automation AI. 
        Analyze the provided recruiter email (which is either provided as raw text or as a screenshot image).
        Extract application details for the student's placement tracking.
        
        Extract the following:
        1. "company_name": Name of the company recruiting.
        2. "role_title": The job/position/role name (e.g. "Software Engineer").
        3. "status": The current status based on the email content. Must be one of these exact values: "Applied", "OA" (if they got an online assessment), "Interview" (if invited for interview rounds), "Offer" (if they got a job offer), "Rejected" (if rejected).
        4. "deadline_date": If a deadline is mentioned for an OA, form, or schedule, extract/convert it to "YYYY-MM-DD HH:MM:SS" format. Else null.
        5. "application_link": Any links mentioned to submit OAs or schedule interviews. Else null.
        6. "is_interview_update": Boolean representing whether this email schedules an interview round or online assessment.
        7. "interview_round": If "is_interview_update" is true, extract these details:
           - "round_number": Round number (e.g. 1 if not specified, or parse from text).
           - "round_type": One of: "Online Assessment", "Technical Interview", "Behavioral Interview", "System Design", "HR Round", "Other".
           - "scheduled_time": The scheduled date/time of the interview in "YYYY-MM-DD HH:MM:SS" format. Else null.
           - "notes": Any crucial details, recruiter name, preparation links, or instructions from the email.
        8. "email_summary": A very brief 1-sentence summary of the email context.

        Your response must be in valid JSON matching this schema:
        {
          "company_name": "Company Name",
          "role_title": "Role Title",
          "status": "Applied" | "OA" | "Interview" | "Offer" | "Rejected",
          "deadline_date": "YYYY-MM-DD HH:MM:SS" or null,
          "application_link": "URL" or null,
          "is_interview_update": true or false,
          "interview_round": {
            "round_number": 1,
            "round_type": "Online Assessment" | "Technical Interview" | "Behavioral Interview" | "System Design" | "HR Round" | "Other",
            "scheduled_time": "YYYY-MM-DD HH:MM:SS" or null,
            "notes": "notes text"
          },
          "email_summary": "summary text"
        }

        Provide ONLY valid JSON. Do not wrap the JSON in markdown code blocks or add any other text.
        """
        
        contents = []
        if screenshot_file and screenshot_file.filename != '':
            img_bytes = screenshot_file.read()
            mime_type = screenshot_file.mimetype
            contents.append({
                "mime_type": mime_type,
                "data": img_bytes
            })
            session['parsed_email_text'] = "[Parsed from screenshot image]"
        else:
            contents.append(email_text)
            session['parsed_email_text'] = email_text
            
        contents.append(prompt)
        
        response = model.generate_content(contents)
        response_text = response.text.strip()
        
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()
            
        parsed_json = json.loads(response_text)
        session['parsed_data'] = parsed_json
        flash("Email successfully analyzed! Verify the extracted details on the right.", "success")
        
    except Exception as e:
        flash(f"Gemini email parser failed: {str(e)}", "error")
        session.pop('parsed_data', None)
        
    return redirect(url_for('fast_register'))

@app.route('/fast-register/confirm', methods=['POST'])
def fast_register_confirm():
    matching_app_id = request.form.get('matching_app_id')
    company_name = request.form.get('company_name', '').strip()
    role_title = request.form.get('role_title', '').strip()
    status = request.form.get('status', 'Applied')
    deadline_date = request.form.get('deadline_date', '').strip() or None
    application_link = request.form.get('application_link', '').strip() or None
    
    is_interview_update = request.form.get('is_interview_update') == 'on'
    round_number = request.form.get('round_number', type=int)
    round_type = request.form.get('round_type')
    scheduled_time = request.form.get('scheduled_time', '').strip() or None
    notes = request.form.get('notes', '')
    
    if not company_name or not role_title:
        flash("Company name and Role title are required.", "error")
        return redirect(url_for('fast_register'))
        
    try:
        app_id = None
        if matching_app_id:
            app_id = int(matching_app_id)
            db.update_application(
                app_id=app_id,
                company_name=company_name,
                role_title=role_title,
                status=status,
                deadline_date=deadline_date,
                application_link=application_link
            )
            flash(f"Application for {company_name} successfully updated!", "success")
        else:
            app_id = db.create_application(
                company_name=company_name,
                role_title=role_title,
                status=status,
                deadline_date=deadline_date,
                application_link=application_link
            )
            flash(f"New application for {company_name} successfully registered!", "success")
            
        if is_interview_update and app_id and round_number and round_type:
            db.add_interview_round(
                application_id=app_id,
                round_number=round_number,
                round_type=round_type,
                scheduled_time=scheduled_time,
                notes=notes
            )
            flash(f"Interview round {round_number} ({round_type}) successfully scheduled!", "success")
            
        session.pop('parsed_data', None)
        session.pop('parsed_email_text', None)
        
    except Exception as e:
        flash(f"Failed to register details: {str(e)}", "error")
        
    return redirect(url_for('dashboard'))

@app.route('/analytics')
def analytics_dashboard():
    conn = get_db()
    
    # Fetch all applications (includes company industry and location)
    apps = db.get_all_applications(conn=conn)
    # Fetch all interview rounds
    all_rounds = db.get_all_interview_rounds(conn=conn)
    
    total_apps = len(apps)
    offer_count = 0
    rejected_count = 0
    in_progress_count = 0
    applied_count = 0
    
    match_scores = []
    success_match_scores = []
    rejected_match_scores = []
    
    industry_counts = {}
    location_counts = {}
    round_type_counts = {}
    
    # Build set of application IDs with scheduled/completed rounds
    apps_with_rounds = set(r['application_id'] for r in all_rounds)
    
    for app in apps:
        status = app['status']
        score = app['jd_match_score'] or 0.0
        
        # 1. Status count
        if status == 'Offer':
            offer_count += 1
        elif status == 'Rejected':
            rejected_count += 1
        elif status == 'In Progress':
            in_progress_count += 1
        else:
            applied_count += 1
            
        # 2. Collect match scores
        if score > 0.0:
            match_scores.append(score)
            if status in ['Offer', 'In Progress'] or app['id'] in apps_with_rounds:
                success_match_scores.append(score)
            if status == 'Rejected':
                rejected_match_scores.append(score)
                
        # 3. Industry counts
        industry = (app['industry_focus'] or 'Technology').strip()
        industry_counts[industry] = industry_counts.get(industry, 0) + 1
        
        # 4. Location counts
        location = (app['company_location'] or 'Remote').strip()
        location_counts[location] = location_counts.get(location, 0) + 1
        
    # 5. Funnel Progress Counts
    # Stage 2: Assessment (status in In Progress/Offer/Rejected OR has at least 1 interview round)
    oa_count = sum(1 for a in apps if a['status'] != 'Applied' or a['id'] in apps_with_rounds)
    
    # Stage 3: Interview (has rounds of type other than OA or status Offer)
    interview_count = 0
    for a in apps:
        has_formal_round = any(
            r['application_id'] == a['id'] and r['round_type'] not in ['Online Assessment', 'OA'] 
            for r in all_rounds
        )
        if has_formal_round or a['status'] == 'Offer':
            interview_count += 1
            
    # Stage 4: Offer (status Offer)
    # Already computed in offer_count
    
    # Calculate conversion metrics
    interview_conv_rate = (interview_count / total_apps * 100.0) if total_apps > 0 else 0.0
    offer_rate = (offer_count / total_apps * 100.0) if total_apps > 0 else 0.0
    
    avg_match_score = (sum(match_scores) / len(match_scores)) if match_scores else 0.0
    avg_success_match_score = (sum(success_match_scores) / len(success_match_scores)) if success_match_scores else 0.0
    avg_rejected_match_score = (sum(rejected_match_scores) / len(rejected_match_scores)) if rejected_match_scores else 0.0
    
    # Clean/Sort Distributions
    sorted_industries = sorted(industry_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    for r in all_rounds:
        rtype = (r['round_type'] or 'Other').strip()
        round_type_counts[rtype] = round_type_counts.get(rtype, 0) + 1
    sorted_round_types = sorted(round_type_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Structured funnel metrics
    funnel = {
        'applied': {
            'count': total_apps,
            'pct': 100.0 if total_apps > 0 else 0.0
        },
        'assessment': {
            'count': oa_count,
            'pct': (oa_count / total_apps * 100.0) if total_apps > 0 else 0.0
        },
        'interview': {
            'count': interview_count,
            'pct': (interview_count / total_apps * 100.0) if total_apps > 0 else 0.0
        },
        'offer': {
            'count': offer_count,
            'pct': (offer_count / total_apps * 100.0) if total_apps > 0 else 0.0
        }
    }
    
    analytics_data = {
        'total_apps': total_apps,
        'offer_count': offer_count,
        'rejected_count': rejected_count,
        'in_progress_count': in_progress_count,
        'applied_count': applied_count,
        
        'interview_conv_rate': interview_conv_rate,
        'offer_rate': offer_rate,
        
        'avg_match_score': avg_match_score,
        'avg_success_match_score': avg_success_match_score,
        'avg_rejected_match_score': avg_rejected_match_score,
        
        'industries': sorted_industries,
        'locations': sorted_locations,
        'round_types': sorted_round_types,
        'funnel': funnel
    }
    
    return render_template('analytics.html', data=analytics_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

