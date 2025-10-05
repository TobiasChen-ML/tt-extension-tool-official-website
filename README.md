TikTok Lingxi Extension Official Website (Backend)
https://listingcopilot.top

Introduction
- This project is the official website and backend services for TikTok Lingxi, providing text cleaning, word classification, and brand extraction APIs, along with basic admin pages and site templates.
- The goal is to offer reliable text-processing capabilities and data support for browser extensions or external applications.

About Me
- I am a Python/Django developer focused on backend engineering and API design.
- I build production-ready services with an emphasis on reliability and maintainability. My common tools include Django, REST, SQL, Docker, and Nginx.
- 🔗 LinkedIn: https://www.linkedin.com/in/jiawei-chen-4095802a9/ | GitHub: https://github.com/JackyFuHk
- 📧 tobiaschannel1999@gmail.com

Project Background
- TikTok Lingxi requires a robust backend to support text cleaning and word processing, including sensitive-word filtering, brand recognition, synonym judgment, and batch processing.
- This project exposes those capabilities via HTTP APIs and integrates an admin interface for basic operations and configuration.

Tech Stack
- Backend Framework: Django (Python)
- Database: SQLite (development); switchable to PostgreSQL/MySQL (production)
- Templates & Static Assets: Django Templates with `static/` and `templates/`
- Third-Party APIs: DeepSeek text processing (for brand extraction, synonym checks, etc.)
- Deployment: Gunicorn/Uvicorn + Nginx (Linux); local development uses `runserver`

Project Structure
```
e:/MyCode/tt-extension-tool-official-website/
├── core/                 # Business logic (views, models, routes)
│   ├── models.py         # Data models
│   ├── views.py          # Views and API implementations
│   ├── urls.py           # Business routes
│   └── management/       # Management commands (data import, etc.)
├── tkspeed/              # Django project configuration (settings, urls, wsgi)
├── templates/            # Page templates
├── static/               # Static assets
├── requirements.txt      # Dependencies
├── manage.py             # Django management entry
└── README.md             # Project documentation (this file)
```

Quick Start (Local Development)
1) Prepare Environment
- Install Python 3.9+ (recommend 3.10/3.11)
- Create and activate a virtual environment at the project root:
  - Windows (PowerShell):
    ```powershell
    python -m venv venv
    .\venv\Scripts\activate
    ```
  - macOS/Linux (bash/zsh):
    ```bash
    python3 -m venv venv && source venv/bin/activate
    ```

2) Install Dependencies
```bash
pip install -r requirements.txt
```

3) Initialize Database
```bash
python manage.py migrate
```

4) Optional: Create Superuser (for admin login)
```bash
python manage.py createsuperuser
```

5) Run the Development Server
```bash
python manage.py runserver
```
- Default: `http://127.0.0.1:8000/`

Environment Variables & Configuration
- If `.env copy.example` exists at the project root, copy it to `.env` and fill in required variables (e.g., external API keys, database settings).
- For production, prefer OS-level environment variables or a secure secret-management solution.

API Overview (Examples)
- Batch Text Cleaning: `POST /api/words/clean_multi/batch`
  - Example JSON request:
    ```json
    {
      "texts": ["Please input text 1", "Please input text 2"]
    }
    ```
  - Returns a list of cleaned texts or structured results.
- Single Text Cleaning: `POST /api/words/clean_multi`
  - Example JSON request:
    ```json
    {
      "text": "Please input text"
    }
    ```

Production Deployment
- Use `gunicorn`/`uvicorn` behind `nginx`, and collect static files to `staticfiles/`.
- Configure longer upstream timeouts to accommodate third-party API latency (e.g., 20–30 seconds). Consider:
  - Retry and graceful degradation strategies
  - Idempotency keys and request de-duplication (batch endpoints)
  - Structured logging and request tracing (trace_id)

License
- See `LICENSE` at the repository root.

Acknowledgements
- README structure and presentation inspired by the open-source project Django-Vectorizer-Web.
- Reference: https://github.com/TobiasChen-ML/Django-Vectorizer-Web/blob/main/README.md