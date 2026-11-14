# AI Hackaton

A minimal FastAPI web project with SQLite-backed authentication.

## Architecture

The project now uses a modular monolith layering:

* `app/main.py` - app bootstrap and router registration
* `app/routers/auth.py` - auth, dashboard, and users HTTP routes
* `app/routers/fixed_assets.py` - fixed asset HTTP routes
* `app/routers/categories.py` - fixed asset category HTTP routes
* `app/views/pages.py` - server-rendered HTML page helpers
* `app/views/templates/` - Jinja2 templates for auth, users, fixed assets, and category pages
* `app/static/app.css` - shared stylesheet (sidebar layout, design tokens, tables, forms), served at `/static/app.css`
* `app/services/auth_service.py` - auth/session business logic
* `app/services/fixed_assets_service.py` - fixed asset business rules (validation, filters, pagination normalization)
* `app/repositories/auth_repository.py` - auth/session data access abstraction
* `app/repositories/fixed_assets_repository.py` - fixed asset and category data access abstraction
* `app/db.py` - SQLite schema management and lower-level DB operations
* `app/config.py` - environment-based settings (production mode, storage paths, admin account, email)
* `app/services/email_service.py` - sends password reset emails over SMTP
* `app/logging_config.py` - logging setup, request context and the `audit()` helper

Layering rule:

* Routes call services/repositories.
* Services contain business logic and input normalization.
* Repositories isolate persistence calls.

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
* `/users` - protected list of all registered users
* `/fixed-assets` - protected fixed assets management page
* `/fixed-assets/add` - separate page for adding a fixed asset
* `/fixed-assets/id/{fixed_asset_id}` - fixed asset details page
* `/fixed-assets/id/{fixed_asset_id}/edit` - fixed asset edit page
* `/fixed-asset-categories` - fixed asset category management page
* `/fixed-asset-categories/{category_id}/edit` - fixed asset category edit page
* `/logout` - clear the active session

Fixed assets page supports paging query parameters:

* `page` (default `1`)
* `page_size` (default `20`, max `100`)

Fixed assets page also supports filtering by:

* `name`
* `category`
* `initial_value`
* `responsible_person`
* `registration_date_from`
* `registration_date_to`

`registration_date_from` and `registration_date_to` form a date interval filter.

## Database

The app creates `app.db` automatically on startup and stores:

* users
* hashed passwords
* sessions
* password reset tokens
* fixed assets
* fixed asset categories

## FixedAsset entity

The project now includes `FixedAsset` with these properties:

* `Id` - GUID
* `Name` - Text (max 100)
* `CategoryId` - GUID (linked to `FixedAssetCategory.Id`)
* `InitialValue` - Number
* `ResponsiblePerson` - Text (max 100)
* `RegistrationDate` - Date (`YYYY-MM-DD`)

`FixedAsset` create/edit forms use category dropdowns populated from `FixedAssetCategory`.

## FixedAssetCategory entity

The project includes `FixedAssetCategory` with these properties:

* `Id` - GUID
* `Category name` - Text (max 100)

Default login credentials are created automatically for local testing:

* Email: `admin@example.com`
* Password: `password123`

Password reset links are shown on screen after you submit the email address, which keeps the project self-contained without an email service.

Both of these apply to local development only. With `APP_ENV=production` the demo account is not created and reset links are emailed instead (see below).

## Running in production

Set `APP_ENV=production` and run without `--reload`, behind HTTPS (most hosts provide it):

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

In production the app:

* does not create the demo account `admin@example.com` / `password123`, and refuses to start if a database still contains that account with the demo password (for example a development `app.db` copied to the server);
* creates the first admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` if that user doesn't exist yet (an existing user's password is never overwritten);
* emails password reset links when SMTP is configured, answering the same way whether or not the email is registered; without SMTP, password reset is turned off;
* sets `Secure` and `SameSite=Strict` on the session cookie and sends HSTS and other security headers;
* turns off the API docs at `/docs`, `/redoc` and `/openapi.json`;
* hides the demo-credentials hint on the login page.

Registration at `/register` stays open to everyone.

### Configuration

All settings are environment variables. None are needed for local development.

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `production` turns on the production behaviour above | development |
| `DATABASE_PATH` | SQLite file; put it on a persistent disk | `app.db` in the project folder |
| `UPLOADS_DIR` | Folder for asset images; put it on a persistent disk | `app/uploads` |
| `ADMIN_EMAIL` | First admin account, created on startup if missing | — |
| `ADMIN_PASSWORD` | Its password, at least 12 characters | — |
| `ADMIN_EMAILS` | Comma-separated emails allowed admin-only actions, such as reopening closed inventory sessions | `ADMIN_EMAIL` in production, `admin@example.com` in development |
| `APP_BASE_URL` | Public URL used in emailed links, e.g. `https://assets.example.com` | — |
| `SMTP_HOST` | Mail server for password reset emails | — (reset off in production) |
| `SMTP_PORT` | Mail server port | `587` |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Mail server login, if required | — |
| `SMTP_FROM` | Sender, e.g. `Asset Registry <noreply@example.com>` | — |
| `SMTP_STARTTLS` | Use STARTTLS | `true` |
| `SESSION_COOKIE_SECURE` | Override the cookie `Secure` flag | `true` in production |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR` | `INFO` |
| `LOG_FORMAT` | `text` (readable) or `json` (one JSON object per line, for log services) | `text`, `json` in production |

Password reset by email needs `SMTP_HOST`, `SMTP_FROM` and `APP_BASE_URL`.

Back up the database file and the uploads folder: they hold all the data.

## Logging

All logs go to the console (stdout); hosting platforms collect it automatically. Setup is in `app/logging_config.py`.

* **Requests** (`app.request`): one line per request with method, path, status, duration and user. Static files are skipped. Each request gets an ID, shown in every log line it produces and returned in the `X-Request-ID` response header.
* **Errors** (`app.error`): unhandled exceptions are logged with their traceback. The user sees a "Something went wrong" page with the request ID as a reference.
* **Audit** (`audit`): who did what. Covers logins (including failed ones), logout, registration, password reset requests and completions; asset create/update/delete (updates list changed fields as `[old, new]`); category create/rename/delete; and inventory session create/update/start/complete/cancel/reopen/delete and PDF report downloads.

Passwords, session cookies and password reset tokens are never logged; reset links appear as `/reset-password/***`. Audit lines contain user emails and responsible-person names, which are personal data: keep logs only as long as you need them.

To add an audit event in new code:

```python
from app.logging_config import audit

audit("asset.transferred", asset_id=asset_id, to_person=new_person)
```
