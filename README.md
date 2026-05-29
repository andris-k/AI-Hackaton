# AI Hackaton

A minimal FastAPI web project with SQLite-backed authentication.

## Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the development server:

```bash
uvicorn app.main:app --reload
```

4. Open `http://127.0.0.1:8000/` in your browser.

## Login flow

The home page checks the current session cookie first. If the user is authenticated, the protected dashboard opens; otherwise the login form is shown.

Submitted credentials are checked against the SQLite database, and successful logins create a session record in the database plus an HTTP-only cookie.

## Auth routes

* `/` - login or dashboard, depending on session state
* `/register` - create a new user account
* `/forgot-password` - generate a local password reset link
* `/reset-password/{token}` - set a new password using a reset token
* `/dashboard` - protected dashboard for signed-in users
* `/logout` - clear the active session

## Database

The app creates `app.db` automatically on startup and stores:

* users
* hashed passwords
* sessions
* password reset tokens

Default login credentials are created automatically for local testing:

* Email: `admin@example.com`
* Password: `password123`

Password reset links are shown on screen after you submit the email address, which keeps the project self-contained without an email service.
