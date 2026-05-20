import json
from fpdf import FPDF

class ResumePDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def sanitize_for_pdf(data):
    if isinstance(data, dict):
        return {k: sanitize_for_pdf(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_pdf(item) for item in data]
    elif isinstance(data, str):
        # Common smart quotes and punctuation replacements to prevent CP1252/Latin-1 crashes in standard FPDF
        replacements = {
            '\u201c': '"',  # Left smart double quote
            '\u201d': '"',  # Right smart double quote
            '\u2018': "'",  # Left smart single quote
            '\u2019': "'",  # Right smart single quote
            '\u2013': '-',  # En dash
            '\u2014': '-',  # Em dash
            '\u2022': '-',  # Bullet point character
            '\u00a0': ' ',  # Non-breaking space
            '\uf0b7': '-',  # Common MS Word bullet point character
        }
        for old, new in replacements.items():
            data = data.replace(old, new)
        return data.encode('latin-1', 'replace').decode('latin-1')
    return data

def generate_resume_pdf(resume_data, output_path):
    """
    Generates a professional resume PDF from structured JSON data.
    """
    # Sanitize input data to prevent font encoding crashes
    resume_data = sanitize_for_pdf(resume_data)
    
    pdf = ResumePDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 1. Header (Name & Contact info)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, resume_data.get("name", "Adit Kumar").upper(), align="C")
    pdf.ln(10)
    
    # Contact details row
    contact = resume_data.get("contact", {})
    details = []
    if contact.get("email"):
        details.append(contact["email"])
    if contact.get("phone"):
        details.append(contact["phone"])
    if contact.get("location"):
        details.append(contact["location"])
    if contact.get("linkedin"):
        details.append(contact["linkedin"])
    if contact.get("github"):
        details.append(contact["github"])
    if contact.get("portfolio"):
        details.append(contact["portfolio"])
        
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    contact_str = "  |  ".join(details)
    pdf.cell(0, 6, contact_str, align="C")
    pdf.ln(8)
    
    # Draw a divider line
    pdf.set_line_width(0.5)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    
    # Helper to draw Section Headers
    def draw_section_header(title):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, title.upper())
        pdf.ln(6)
        pdf.set_line_width(0.2)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(2)
        
    # 2. Professional Summary
    summary = resume_data.get("summary", "")
    if summary:
        draw_section_header("Professional Summary")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 5, summary)
        pdf.ln(1)
        
    # 3. Work Experience
    experience = resume_data.get("experience", [])
    if experience:
        draw_section_header("Work Experience")
        for exp in experience:
            # Row 1: Company (Left) & Dates (Right)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(100, 5, exp.get("company", ""), align="L")
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(80, 5, exp.get("dates", ""), align="R")
            pdf.ln(5)
            
            # Row 2: Role (Left) & Location (Right)
            pdf.set_font("Helvetica", "I", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(100, 5, exp.get("role", ""), align="L")
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(80, 5, exp.get("location", ""), align="R")
            pdf.ln(6)
            
            # Bullets
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(40, 40, 40)
            for bullet in exp.get("bullets", []):
                pdf.set_x(20)
                pdf.write(4, "-  ")
                pdf.multi_cell(165, 4, bullet)
            pdf.ln(2)
            
    # 4. Projects
    projects = resume_data.get("projects", [])
    if projects:
        draw_section_header("Projects")
        for proj in projects:
            # Row 1: Project Name (Left) & Dates (Right)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 0, 0)
            
            stack = proj.get("tech_stack", "")
            title_text = proj.get("name", "")
            if stack:
                title_text += f" ({stack})"
                
            pdf.cell(120, 5, title_text, align="L")
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(60, 5, proj.get("dates", ""), align="R")
            pdf.ln(6)
            
            # Bullets
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(40, 40, 40)
            for bullet in proj.get("bullets", []):
                pdf.set_x(20)
                pdf.write(4, "-  ")
                pdf.multi_cell(165, 4, bullet)
            pdf.ln(2)
            
    # 5. Education
    education = resume_data.get("education", [])
    if education:
        draw_section_header("Education")
        for edu in education:
            # Row 1: Institution (Left) & Dates (Right)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(100, 5, edu.get("institution", ""), align="L")
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(80, 5, edu.get("dates", ""), align="R")
            pdf.ln(5)
            
            # Row 2: Degree & GPA (Left) & Location (Right)
            pdf.set_font("Helvetica", "I", 9.5)
            pdf.set_text_color(40, 40, 40)
            deg_text = edu.get("degree", "")
            gpa = edu.get("gpa", "")
            if gpa:
                deg_text += f" (GPA: {gpa})"
            pdf.cell(100, 5, deg_text, align="L")
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(80, 5, edu.get("location", ""), align="R")
            pdf.ln(6)
            
    # 6. Skills
    skills = resume_data.get("skills", {})
    if skills:
        draw_section_header("Technical Skills")
        
        # Determine if it's a dict or list
        if isinstance(skills, dict):
            for cat, items in skills.items():
                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_text_color(0, 0, 0)
                pdf.write(5, f"{cat}: ")
                
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(40, 40, 40)
                if isinstance(items, list):
                    items_str = ", ".join(items)
                else:
                    items_str = str(items)
                pdf.write(5, items_str + "\n")
        elif isinstance(skills, list):
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5, ", ".join(skills))
            
    # Save the generated PDF file
    pdf.output(output_path)
    print(f"PDF successfully generated at: {output_path}")

if __name__ == '__main__':
    # Test execution
    test_data = {
        "name": "Adit Kumar",
        "contact": {
            "email": "adit@example.com",
            "phone": "+91 98765 43210",
            "location": "Bangalore, India",
            "linkedin": "linkedin.com/in/adit",
            "github": "github.com/adit"
        },
        "summary": "Highly motivated and results-oriented Software Engineering student with experience developing full-stack web applications and integrating advanced Gemini AI models.",
        "skills": {
            "Languages": ["Python", "SQL", "JavaScript", "C++"],
            "Frameworks": ["Flask", "Tailwind CSS", "Bootstrap"],
            "Tools": ["Git", "Docker", "VS Code", "SQLite"]
        }
    }
    generate_resume_pdf(test_data, "test_resume.pdf")
