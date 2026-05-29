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
