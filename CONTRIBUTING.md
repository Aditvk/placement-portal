# Contributing to Adit's Placement Portal

Thank you for your interest in contributing! Here's how you can get started.

## 🛠️ Development Setup

1. **Fork** the repository and clone it locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/placement-portal.git
   cd placement-portal
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Gemini API key
   ```

4. **Run the development server:**
   ```bash
   python app.py
   ```

5. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## 📁 Project Structure

| File / Directory | Purpose |
|------------------|---------|
| `app.py` | Flask application — all routes, Gemini API calls, and background scheduler |
| `db.py` | SQLite database connection manager and CRUD helper functions |
| `pdf_generator.py` | FPDF2-based Harvard-standard resume PDF builder |
| `schema.sql` | Database schema definitions (companies, applications, interview_rounds) |
| `seed.sql` | Initial seed data for demo/testing |
| `templates/` | Jinja2 HTML templates following the Neo-Brutalist design system |
| `render.yaml` | Render.com deployment blueprint |

## 🔀 Pull Request Guidelines

- Create a feature branch from `main` (`git checkout -b feature/my-feature`)
- Keep changes focused — one feature or fix per PR
- Test all routes render correctly before submitting
- Do not commit `.env`, `placement.db`, or compiled PDF files

## 🐛 Reporting Issues

Open a GitHub Issue with:
- Steps to reproduce the bug
- Expected vs actual behavior
- Screenshots if it's a UI issue
- Your Python version and OS

## 📜 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
