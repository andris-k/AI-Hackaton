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
