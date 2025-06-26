LEAVE APPLICATION - DJANGO PROJECT

SETUP INSTRUCTIONS
==================

1. Clone the repository:
   git clone <your-repo-url>

2. Create and activate a virtual environment:
   python3 -m venv venv
   source venv/bin/activate

3. Install dependencies:
   pip install -r requirements.txt

4. Set up environment variables:
   - Copy .env.example to .env and fill in your Slack credentials.

5. Run migrations:
   python manage.py migrate

6. Create a superuser (optional, for admin access):
   python manage.py createsuperuser

7. Start the development server:
   python manage.py runserver

8. Access the app via Slack commands and the Django admin at /admin/

NOTES
=====
- All code is inside the 'leave' Django app.
- Use requirements.txt for dependencies.
- Use .env for secrets (never commit .env to git).
- All migrations are tracked except for __init__.py.
- Static and media files are ignored by git.

Enjoy your leave management system!
