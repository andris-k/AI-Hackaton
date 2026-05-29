from html import escape
from datetime import datetime
from urllib.parse import urlencode

from fastapi import Cookie, FastAPI, Form, Query
from fastapi.responses import HTMLResponse

from app.db import (
    count_fixed_assets,
    create_fixed_asset,
    create_fixed_asset_category,
    create_password_reset_token,
    create_session,
    create_user,
    delete_fixed_asset_category,
    delete_session,
    delete_sessions_for_user,
    ensure_default_user,
    get_fixed_asset_category_by_id,
    get_fixed_asset_by_id,
    get_password_reset_token,
    get_session,
    get_user_by_email,
    get_user_by_id,
    get_user_by_session_token,
    initialize_database,
    list_fixed_asset_categories,
    list_fixed_asset_categories_with_usage,
    list_fixed_assets,
    list_users,
    mark_password_reset_token_used,
    update_fixed_asset_category,
    update_fixed_asset,
    update_user_password,
    verify_password,
)

app = FastAPI(title="AI Hackaton")

SESSION_COOKIE_NAME = "session_token"
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    ensure_default_user()


def render_page(
    page_title: str,
    heading: str,
    subtitle: str,
    content: str,
    *,
    width: str = "440px",
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    message_block = f'<p class="message {message_kind}">{escape(message)}</p>' if message else ""

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{escape(page_title)}</title>
            <style>
                :root {{
                    color-scheme: light;
                    font-family: Inter, "Segoe UI", Arial, sans-serif;
                    --bg: #0f172a;
                    --panel: rgba(255, 255, 255, 0.96);
                    --text: #0f172a;
                    --muted: #64748b;
                    --accent: #2563eb;
                    --accent-hover: #1d4ed8;
                    --border: #dbe4f0;
                    --success: #166534;
                    --error: #b91c1c;
                    --info: #1d4ed8;
                    --shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
                }}

                * {{ box-sizing: border-box; }}

                body {{
                    margin: 0;
                    min-height: 100vh;
                    display: grid;
                    place-items: center;
                    background:
                        radial-gradient(circle at top, rgba(37, 99, 235, 0.35), transparent 28%),
                        linear-gradient(135deg, #0f172a, #111827 55%, #1e293b);
                    color: var(--text);
                    padding: 24px;
                }}

                .card {{
                    width: min(100%, {width});
                    background: var(--panel);
                    border: 1px solid rgba(255, 255, 255, 0.45);
                    border-radius: 24px;
                    box-shadow: var(--shadow);
                    padding: 32px;
                }}

                .eyebrow {{
                    margin: 0 0 12px;
                    color: var(--accent);
                    font-size: 0.85rem;
                    font-weight: 700;
                    letter-spacing: 0.12em;
                    text-transform: uppercase;
                }}

                h1 {{
                    margin: 0 0 10px;
                    font-size: 2rem;
                    line-height: 1.1;
                }}

                p.subtitle {{
                    margin: 0 0 24px;
                    color: var(--muted);
                    line-height: 1.5;
                }}

                .message {{
                    margin: 0 0 16px;
                    padding: 12px 14px;
                    border-radius: 12px;
                    font-size: 0.95rem;
                }}

                .message.info {{ background: rgba(37, 99, 235, 0.08); color: var(--info); }}
                .message.success {{ background: rgba(22, 101, 52, 0.08); color: var(--success); }}
                .message.error {{ background: rgba(185, 28, 28, 0.08); color: var(--error); }}

                label {{
                    display: block;
                    margin: 0 0 8px;
                    font-size: 0.95rem;
                    font-weight: 600;
                }}

                .field {{ margin-bottom: 18px; }}

                input, select {{
                    width: 100%;
                    border: 1px solid var(--border);
                    border-radius: 14px;
                    padding: 14px 16px;
                    font-size: 1rem;
                    outline: none;
                    transition: border-color 0.2s ease, box-shadow 0.2s ease;
                }}

                input:focus, select:focus {{
                    border-color: var(--accent);
                    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
                }}

                button {{
                    width: 100%;
                    border: 0;
                    border-radius: 14px;
                    padding: 14px 16px;
                    background: linear-gradient(135deg, var(--accent), #1e40af);
                    color: white;
                    font-size: 1rem;
                    font-weight: 700;
                    cursor: pointer;
                    transition: transform 0.15s ease, filter 0.15s ease;
                }}

                button:hover {{
                    filter: brightness(1.05);
                    transform: translateY(-1px);
                }}

                .links {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 12px;
                    margin-top: 18px;
                }}

                .links a {{
                    color: var(--accent);
                    font-weight: 600;
                    text-decoration: none;
                }}

                .links a:hover {{
                    color: var(--accent-hover);
                    text-decoration: underline;
                }}

                .small {{
                    margin-top: 16px;
                    color: var(--muted);
                    font-size: 0.9rem;
                    line-height: 1.5;
                }}

                .stack {{ display: grid; gap: 14px; }}

                .panel {{
                    border: 1px solid var(--border);
                    border-radius: 18px;
                    padding: 18px;
                    background: rgba(255, 255, 255, 0.72);
                }}

                .panel h2 {{
                    margin: 0 0 10px;
                    font-size: 1.05rem;
                }}

                code {{
                    display: block;
                    margin-top: 12px;
                    padding: 12px 14px;
                    border-radius: 12px;
                    background: rgba(15, 23, 42, 0.05);
                    overflow-wrap: anywhere;
                }}

                .dashboard-grid {{
                    display: grid;
                    gap: 16px;
                }}

                @media (min-width: 760px) {{
                    .dashboard-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
                    .dashboard-grid .wide {{ grid-column: 1 / -1; }}
                }}
            </style>
        </head>
        <body>
            <main class="card">
                <p class="eyebrow">AI Hackaton</p>
                <h1>{escape(heading)}</h1>
                <p class="subtitle">{escape(subtitle)}</p>
                {message_block}
                {content}
            </main>
        </body>
    </html>
    """

    return HTMLResponse(content=html)


def render_login_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Enter your password" required />
        </div>
        <button type="submit">Log in</button>
    </form>
    <div class="links">
        <a href="/register">Create account</a>
        <a href="/forgot-password">Reset password</a>
    </div>
    <p class="small">Use the seeded local account: admin@example.com / password123.</p>
    """
    return render_page(
        "AI Hackaton Login",
        "Log in",
        "Enter your email and password to access the system.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_register_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/register">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Create a password" required />
        </div>
        <div class="field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" placeholder="Repeat your password" required />
        </div>
        <button type="submit">Create account</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
        <a href="/forgot-password">Reset password</a>
    </div>
    """
    return render_page(
        "AI Hackaton Registration",
        "Create account",
        "Register a new user to access the dashboard.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_forgot_password_page(error: str | None = None, email: str = "") -> HTMLResponse:
    safe_email = escape(email)
    content = f"""
    <form method="post" action="/forgot-password">
        <div class="field">
            <label for="email">Email</label>
            <input id="email" name="email" type="email" value="{safe_email}" placeholder="name@example.com" required />
        </div>
        <button type="submit">Generate reset link</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
        <a href="/register">Create account</a>
    </div>
    <p class="small">For local testing, the reset link is displayed on screen instead of being emailed.</p>
    """
    return render_page(
        "AI Hackaton Password Reset",
        "Reset password",
        "Request a reset link for an existing account.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_reset_password_page(token: str, error: str | None = None) -> HTMLResponse:
    safe_token = escape(token)
    content = f"""
    <form method="post" action="/reset-password/{safe_token}">
        <div class="field">
            <label for="password">New password</label>
            <input id="password" name="password" type="password" placeholder="Enter a new password" required />
        </div>
        <div class="field">
            <label for="confirm_password">Confirm password</label>
            <input id="confirm_password" name="confirm_password" type="password" placeholder="Repeat the new password" required />
        </div>
        <button type="submit">Update password</button>
    </form>
    <div class="links">
        <a href="/">Back to login</a>
    </div>
    """
    return render_page(
        "AI Hackaton Reset Password",
        "Set a new password",
        "Use the reset token to choose a new password.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_dashboard_page(
    user_email: str,
    session_token: str,
    *,
    message: str | None = None,
    message_kind: str = "success",
) -> HTMLResponse:
    safe_email = escape(user_email)
    safe_token = escape(session_token)
    content = f"""
    <div class="dashboard-grid">
        <section class="panel wide">
            <h2>Signed in</h2>
            <p>You are logged in as <strong>{safe_email}</strong>.</p>
            <p>Your authenticated session is stored in SQLite and protected by an HTTP-only cookie.</p>
            <code>Session token: {safe_token}</code>
        </section>
        <section class="panel">
            <h2>Account actions</h2>
            <div class="links" style="margin-top: 0; flex-direction: column; align-items: flex-start;">
                <a href="/fixed-assets">Manage fixed assets</a>
                <a href="/fixed-asset-categories">Manage fixed asset categories</a>
                <a href="/users">View registered users</a>
                <a href="/logout">Log out</a>
                <a href="/forgot-password">Reset password</a>
                <a href="/register">Create another account</a>
            </div>
        </section>
        <section class="panel">
            <h2>Project status</h2>
            <p>The dashboard is protected. Unauthenticated users are returned to the login flow.</p>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Dashboard",
        "Dashboard",
        "Protected workspace for authenticated users.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def set_session_cookie(response: HTMLResponse, session_token: str) -> HTMLResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response


def render_users_page(current_email: str, users: list[object], email_filter: str = "") -> HTMLResponse:
    safe_current_email = escape(current_email)
    safe_email_filter = escape(email_filter)
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(user['id']))}</td>"
        f"<td>{escape(user['email'])}</td>"
        f"<td>{escape(user['created_at'])}</td>"
        "</tr>"
        for user in users
    )
    table = f"""
    <style>
        table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
        }}

        th, td {{
            padding: 12px 10px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 0.95rem;
        }}

        th {{
            background: rgba(37, 99, 235, 0.1);
            font-weight: 700;
        }}

        tr:last-child td {{ border-bottom: 0; }}

        .filter-row {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 10px;
            align-items: end;
            margin-bottom: 14px;
        }}

        .filter-row button {{
            width: auto;
            min-width: 110px;
        }}

        @media (max-width: 640px) {{
            .filter-row {{ grid-template-columns: 1fr; }}
            .filter-row button {{ width: 100%; }}
        }}
    </style>
    <div class="stack">
        <section class="panel wide">
            <h2>Registered users</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="get" action="/users" class="filter-row">
                <div>
                    <label for="email_filter">Filter by email</label>
                    <input
                        id="email_filter"
                        name="email"
                        type="text"
                        value="{safe_email_filter}"
                        placeholder="Type part of an email"
                    />
                </div>
                <button type="submit">Apply filter</button>
            </form>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Email</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <div class="links">
                <a href="/dashboard">Back to dashboard</a>
                <a href="/logout">Log out</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Users",
        "Users",
        "List of registered users in the system.",
        table,
        width="860px",
    )


def render_fixed_assets_page(
    current_email: str,
    fixed_assets: list[object],
    *,
    page: int,
    page_size: int,
    total_assets: int,
    filters: dict[str, str],
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    safe_name = escape(filters.get("name", ""))
    safe_category = escape(filters.get("category", ""))
    safe_initial_value = escape(filters.get("initial_value", ""))
    safe_responsible_person = escape(filters.get("responsible_person", ""))
    safe_registration_date_from = escape(filters.get("registration_date_from", ""))
    safe_registration_date_to = escape(filters.get("registration_date_to", ""))

    rows = "".join(
        "<tr>"
        f"<td><a href=\"/fixed-assets/id/{escape(asset['id'])}\">{escape(asset['id'])}</a></td>"
        f"<td><a href=\"/fixed-assets/id/{escape(asset['id'])}\">{escape(asset['name'])}</a></td>"
        f"<td>{escape(asset['category'])}</td>"
        f"<td>{escape('{:.2f}'.format(float(asset['initial_value'])))}</td>"
        f"<td>{escape(asset['responsible_person'])}</td>"
        f"<td>{escape(asset['registration_date'])}</td>"
        f"<td><a href=\"/fixed-assets/id/{escape(asset['id'])}/edit\">Edit</a></td>"
        "</tr>"
        for asset in fixed_assets
    )
    total_pages = max((total_assets + page_size - 1) // page_size, 1)
    previous_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages
    start_row = (page - 1) * page_size + 1 if total_assets > 0 else 0
    end_row = min(page * page_size, total_assets)

    base_query = {
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value": filters.get("initial_value", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    def page_link(target_page: int) -> str:
        query = {**base_query, "page": str(target_page)}
        return f"/fixed-assets?{urlencode(query)}"

    add_asset_query = {**base_query, "page": str(page)}

    prev_link = (
        f'<a href="{page_link(previous_page)}">Previous</a>'
        if page > 1
        else '<span style="color: var(--muted);">Previous</span>'
    )
    next_link = (
        f'<a href="{page_link(next_page)}">Next</a>'
        if page < total_pages
        else '<span style="color: var(--muted);">Next</span>'
    )

    content = f"""
    <style>
        .assets-grid {{
            display: grid;
            gap: 16px;
        }}

        .asset-form-row {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }}

        .filter-form {{
            display: grid;
            gap: 12px;
            margin-bottom: 14px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
            font-size: 0.93rem;
        }}

        th, td {{
            padding: 10px 9px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }}

        th {{
            background: rgba(37, 99, 235, 0.1);
            font-weight: 700;
        }}

        tr:last-child td {{ border-bottom: 0; }}

        @media (max-width: 760px) {{
            .asset-form-row {{ grid-template-columns: 1fr; }}
        }}

        .pager {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            margin-top: 14px;
            flex-wrap: wrap;
        }}

        .pager .controls {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}

        .pager .meta {{
            color: var(--muted);
            font-size: 0.9rem;
        }}
    </style>
    <div class="assets-grid">
        <section class="panel">
            <h2>Registered fixed assets</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="get" action="/fixed-assets" class="filter-form">
                <input type="hidden" name="page" value="1" />
                <input type="hidden" name="page_size" value="{page_size}" />
                <div class="asset-form-row">
                    <div>
                        <label for="filter_name">Name</label>
                        <input id="filter_name" name="name" type="text" value="{safe_name}" />
                    </div>
                    <div>
                        <label for="filter_category">Category</label>
                        <input id="filter_category" name="category" type="text" value="{safe_category}" />
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="filter_initial_value">InitialValue</label>
                        <input id="filter_initial_value" name="initial_value" type="number" step="0.01" min="0" value="{safe_initial_value}" />
                    </div>
                    <div>
                        <label for="filter_responsible_person">ResponsiblePerson</label>
                        <input id="filter_responsible_person" name="responsible_person" type="text" value="{safe_responsible_person}" />
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="filter_registration_date_from">RegistrationDate From</label>
                        <input id="filter_registration_date_from" name="registration_date_from" type="date" value="{safe_registration_date_from}" />
                    </div>
                    <div>
                        <label for="filter_registration_date_to">RegistrationDate To</label>
                        <input id="filter_registration_date_to" name="registration_date_to" type="date" value="{safe_registration_date_to}" />
                    </div>
                </div>
                <div class="links" style="margin-top: 0;">
                    <button type="submit">Apply filters</button>
                    <a href="/fixed-assets?page=1&page_size={page_size}">Clear filters</a>
                </div>
            </form>
            <div class="links" style="margin-top: 0; margin-bottom: 12px;">
                <a href="/fixed-assets/add?{urlencode(add_asset_query)}">Add fixed asset</a>
                <a href="/dashboard">Back to dashboard</a>
                <a href="/logout">Log out</a>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Id</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th>InitialValue</th>
                        <th>ResponsiblePerson</th>
                        <th>RegistrationDate</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            <div class="pager">
                <div class="meta">Showing {start_row}-{end_row} of {total_assets}</div>
                <div class="controls">
                    {prev_link}
                    <span>Page {page} / {total_pages}</span>
                    {next_link}
                </div>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Fixed Assets",
        "Fixed Assets",
        "Create and view fixed assets.",
        content,
        width="1100px",
        message=message,
        message_kind=message_kind,
    )


def render_fixed_asset_details_page(
    current_email: str,
    fixed_asset: object,
    *,
    page: int,
    page_size: int,
    filters: dict[str, str],
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    safe_id = escape(fixed_asset["id"])
    safe_name = escape(fixed_asset["name"])
    safe_category = escape(fixed_asset["category"])
    safe_initial_value = escape("{:.2f}".format(float(fixed_asset["initial_value"])))
    safe_responsible_person = escape(fixed_asset["responsible_person"])
    safe_registration_date = escape(fixed_asset["registration_date"])

    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value": filters.get("initial_value", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = f"""
    <div class="stack">
        <section class="panel">
            <h2>Fixed asset details</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <table style="width: 100%; border-collapse: collapse;">
                <tbody>
                    <tr><th style="text-align: left; padding: 8px; width: 220px;">Id</th><td style="padding: 8px;">{safe_id}</td></tr>
                    <tr><th style="text-align: left; padding: 8px;">Name</th><td style="padding: 8px;">{safe_name}</td></tr>
                    <tr><th style="text-align: left; padding: 8px;">Category</th><td style="padding: 8px;">{safe_category}</td></tr>
                    <tr><th style="text-align: left; padding: 8px;">InitialValue</th><td style="padding: 8px;">{safe_initial_value}</td></tr>
                    <tr><th style="text-align: left; padding: 8px;">ResponsiblePerson</th><td style="padding: 8px;">{safe_responsible_person}</td></tr>
                    <tr><th style="text-align: left; padding: 8px;">RegistrationDate</th><td style="padding: 8px;">{safe_registration_date}</td></tr>
                </tbody>
            </table>
            <div class="links">
                <a href="/fixed-assets/id/{safe_id}/edit?{urlencode(back_query)}">Edit fixed asset</a>
                <a href="/fixed-assets?{urlencode(back_query)}">Back to fixed assets</a>
                <a href="/dashboard">Back to dashboard</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Fixed Asset Details",
        "Fixed Asset Details",
        "Detailed view of a fixed asset.",
        content,
        width="860px",
    )


def render_edit_fixed_asset_page(
    current_email: str,
    fixed_asset: object,
    *,
    page: int,
    page_size: int,
    filters: dict[str, str],
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    safe_id = escape(fixed_asset["id"])
    safe_name = escape(fixed_asset["name"])
    safe_category = escape(fixed_asset["category"])
    safe_initial_value = escape("{:.2f}".format(float(fixed_asset["initial_value"])))
    safe_responsible_person = escape(fixed_asset["responsible_person"])
    safe_registration_date = escape(fixed_asset["registration_date"])
    categories = list_fixed_asset_categories()
    selected_category_id = (
        str(fixed_asset["category_id"])
        if "category_id" in fixed_asset.keys() and fixed_asset["category_id"]
        else ""
    )
    category_options = "".join(
        (
            f'<option value="{escape(category["id"])}" selected>{escape(category["name"])}</option>'
            if category["id"] == selected_category_id
            else f'<option value="{escape(category["id"])}">{escape(category["name"])}</option>'
        )
        for category in categories
    )

    safe_name_filter = escape(filters.get("name", ""))
    safe_category_filter = escape(filters.get("category", ""))
    safe_initial_value_filter = escape(filters.get("initial_value", ""))
    safe_responsible_person_filter = escape(filters.get("responsible_person", ""))
    safe_registration_date_from_filter = escape(filters.get("registration_date_from", ""))
    safe_registration_date_to_filter = escape(filters.get("registration_date_to", ""))

    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value": filters.get("initial_value", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = f"""
    <style>
        .asset-form {{
            display: grid;
            gap: 12px;
        }}

        .asset-form-row {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }}

        @media (max-width: 760px) {{
            .asset-form-row {{ grid-template-columns: 1fr; }}
        }}
    </style>
    <div class="stack">
        <section class="panel">
            <h2>Edit fixed asset</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="post" action="/fixed-assets/id/{safe_id}/edit" class="asset-form">
                <input type="hidden" name="page" value="{page}" />
                <input type="hidden" name="page_size" value="{page_size}" />
                <input type="hidden" name="name_filter" value="{safe_name_filter}" />
                <input type="hidden" name="category_filter" value="{safe_category_filter}" />
                <input type="hidden" name="initial_value_filter" value="{safe_initial_value_filter}" />
                <input type="hidden" name="responsible_person_filter" value="{safe_responsible_person_filter}" />
                <input type="hidden" name="registration_date_from_filter" value="{safe_registration_date_from_filter}" />
                <input type="hidden" name="registration_date_to_filter" value="{safe_registration_date_to_filter}" />
                <div class="asset-form-row">
                    <div>
                        <label for="name">Name</label>
                        <input id="name" name="name" type="text" maxlength="100" value="{safe_name}" required />
                    </div>
                    <div>
                        <label for="category">Category</label>
                        <select id="category_id" name="category_id" required>
                            {category_options}
                        </select>
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="initial_value">Initial value</label>
                        <input id="initial_value" name="initial_value" type="number" step="0.01" min="0" value="{safe_initial_value}" required />
                    </div>
                    <div>
                        <label for="responsible_person">Responsible person</label>
                        <input id="responsible_person" name="responsible_person" type="text" maxlength="100" value="{safe_responsible_person}" required />
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="registration_date">Registration date</label>
                        <input id="registration_date" name="registration_date" type="date" value="{safe_registration_date}" required />
                    </div>
                </div>
                <button type="submit">Save changes</button>
            </form>
            <div class="links">
                <a href="/fixed-assets/id/{safe_id}?{urlencode(back_query)}">Back to details</a>
                <a href="/fixed-assets?{urlencode(back_query)}">Back to fixed assets</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Edit Fixed Asset",
        "Edit Fixed Asset",
        "Update fixed asset details.",
        content,
        width="860px",
        message=message,
        message_kind=message_kind,
    )


def render_add_fixed_asset_page(
    current_email: str,
    *,
    page: int,
    page_size: int,
    categories: list[object],
    form_data: dict[str, str] | None = None,
    filters: dict[str, str],
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    form_data = form_data or {}

    safe_name = escape(filters.get("name", ""))
    safe_category = escape(filters.get("category", ""))
    safe_initial_value = escape(filters.get("initial_value", ""))
    safe_responsible_person = escape(filters.get("responsible_person", ""))
    safe_registration_date_from = escape(filters.get("registration_date_from", ""))
    safe_registration_date_to = escape(filters.get("registration_date_to", ""))

    safe_name_value = escape(form_data.get("name", ""))
    safe_initial_value_value = escape(form_data.get("initial_value", ""))
    safe_responsible_person_value = escape(form_data.get("responsible_person", ""))
    safe_registration_date_value = escape(form_data.get("registration_date", ""))
    selected_category_id = form_data.get("category_id", "")
    category_options = "".join(
        (
            f'<option value="{escape(category["id"])}" selected>{escape(category["name"])}</option>'
            if category["id"] == selected_category_id
            else f'<option value="{escape(category["id"])}">{escape(category["name"])}</option>'
        )
        for category in categories
    )

    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value": filters.get("initial_value", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = f"""
    <style>
        .asset-form {{
            display: grid;
            gap: 12px;
        }}

        .asset-form-row {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }}

        @media (max-width: 760px) {{
            .asset-form-row {{ grid-template-columns: 1fr; }}
        }}
    </style>
    <div class="stack">
        <section class="panel">
            <h2>Add fixed asset</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="post" action="/fixed-assets/add" class="asset-form">
                <input type="hidden" name="page" value="{page}" />
                <input type="hidden" name="page_size" value="{page_size}" />
                <input type="hidden" name="name_filter" value="{safe_name}" />
                <input type="hidden" name="category_filter" value="{safe_category}" />
                <input type="hidden" name="initial_value_filter" value="{safe_initial_value}" />
                <input type="hidden" name="responsible_person_filter" value="{safe_responsible_person}" />
                <input type="hidden" name="registration_date_from_filter" value="{safe_registration_date_from}" />
                <input type="hidden" name="registration_date_to_filter" value="{safe_registration_date_to}" />
                <div class="asset-form-row">
                    <div>
                        <label for="name">Name</label>
                        <input id="name" name="name" type="text" maxlength="100" value="{safe_name_value}" required />
                    </div>
                    <div>
                        <label for="category">Category</label>
                        <select id="category_id" name="category_id" required>
                            <option value="">Select category</option>
                            {category_options}
                        </select>
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="initial_value">Initial value</label>
                        <input id="initial_value" name="initial_value" type="number" step="0.01" min="0" value="{safe_initial_value_value}" required />
                    </div>
                    <div>
                        <label for="responsible_person">Responsible person</label>
                        <input id="responsible_person" name="responsible_person" type="text" maxlength="100" value="{safe_responsible_person_value}" required />
                    </div>
                </div>
                <div class="asset-form-row">
                    <div>
                        <label for="registration_date">Registration date</label>
                        <input id="registration_date" name="registration_date" type="date" value="{safe_registration_date_value}" required />
                    </div>
                </div>
                <button type="submit">Save fixed asset</button>
            </form>
            <div class="links">
                <a href="/fixed-assets?{urlencode(back_query)}">Back to fixed assets</a>
                <a href="/dashboard">Back to dashboard</a>
                <a href="/logout">Log out</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Add Fixed Asset",
        "Add Fixed Asset",
        "Create a new fixed asset in the system.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def render_fixed_asset_categories_page(
    current_email: str,
    categories: list[object],
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    rows = "".join(
        "<tr>"
        f"<td>{escape(category['id'])}</td>"
        f"<td>{escape(category['name'])}</td>"
        f"<td>{escape(str(category['assets_count']))}</td>"
        f"<td><a href=\"/fixed-asset-categories/{escape(category['id'])}/edit\">Edit</a></td>"
        f"<td><form method=\"post\" action=\"/fixed-asset-categories/{escape(category['id'])}/delete\" onsubmit=\"return confirm('Delete this category?');\"><button type=\"submit\">Delete</button></form></td>"
        "</tr>"
        for category in categories
    )

    content = f"""
    <div class="stack">
        <section class="panel">
            <h2>Add category</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="post" action="/fixed-asset-categories">
                <div class="field">
                    <label for="category_name">Category name</label>
                    <input id="category_name" name="name" type="text" maxlength="100" required />
                </div>
                <button type="submit">Create category</button>
            </form>
            <div class="links">
                <a href="/dashboard">Back to dashboard</a>
                <a href="/fixed-assets">Back to fixed assets</a>
            </div>
        </section>
        <section class="panel">
            <h2>Existing categories</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr>
                        <th style="text-align: left; padding: 10px;">Id</th>
                        <th style="text-align: left; padding: 10px;">Category name</th>
                        <th style="text-align: left; padding: 10px;">Assets count</th>
                        <th style="text-align: left; padding: 10px;">Edit</th>
                        <th style="text-align: left; padding: 10px;">Delete</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Fixed Asset Categories",
        "Fixed Asset Categories",
        "Create and manage fixed asset categories.",
        content,
        width="980px",
        message=message,
        message_kind=message_kind,
    )


def render_edit_fixed_asset_category_page(
    current_email: str,
    category: object,
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    safe_current_email = escape(current_email)
    safe_id = escape(category["id"])
    safe_name = escape(category["name"])
    content = f"""
    <div class="stack">
        <section class="panel">
            <h2>Edit category</h2>
            <p>Signed in as <strong>{safe_current_email}</strong>.</p>
            <form method="post" action="/fixed-asset-categories/{safe_id}/edit">
                <div class="field">
                    <label for="category_name">Category name</label>
                    <input id="category_name" name="name" type="text" maxlength="100" value="{safe_name}" required />
                </div>
                <button type="submit">Save category</button>
            </form>
            <div class="links">
                <a href="/fixed-asset-categories">Back to categories</a>
                <a href="/fixed-assets">Back to fixed assets</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Edit Fixed Asset Category",
        "Edit Fixed Asset Category",
        "Update fixed asset category name.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def current_user(session_token: str | None) -> tuple[str, object] | None:
    if not session_token:
        return None

    user = get_user_by_session_token(session_token)
    if user is None:
        return None

    return session_token, user


@app.get("/", response_class=HTMLResponse)
def read_root(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is not None:
        _, user = authenticated
        return render_dashboard_page(user["email"], session_token or "")

    return render_login_page()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to access the dashboard.")

    _, user = authenticated
    return render_dashboard_page(user["email"], session_token or "")


@app.get("/users", response_class=HTMLResponse)
def users_page(
    session_token: str | None = Cookie(default=None),
    email: str = Query(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to access the users page.")

    _, user = authenticated
    users = list_users(email)
    return render_users_page(user["email"], users, email)


@app.get("/fixed-assets", response_class=HTMLResponse)
def fixed_assets_page(
    session_token: str | None = Cookie(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str = Query(default=""),
    category: str = Query(default=""),
    initial_value: str = Query(default=""),
    responsible_person: str = Query(default=""),
    registration_date_from: str = Query(default=""),
    registration_date_to: str = Query(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to access fixed assets.")

    _, user = authenticated

    filters = {
        "name": name.strip(),
        "category": category.strip(),
        "initial_value": initial_value.strip(),
        "responsible_person": responsible_person.strip(),
        "registration_date_from": registration_date_from.strip(),
        "registration_date_to": registration_date_to.strip(),
    }

    try:
        if filters["initial_value"]:
            float(filters["initial_value"])
    except ValueError:
        filters["initial_value"] = ""
        total_assets = count_fixed_assets(filters)
        total_pages = max((total_assets + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages)
        assets = list_fixed_assets(current_page, page_size, filters)
        return render_fixed_assets_page(
            user["email"],
            assets,
            page=current_page,
            page_size=page_size,
            total_assets=total_assets,
            filters=filters,
            message="InitialValue filter must be a valid number.",
            message_kind="error",
        )

    try:
        if filters["registration_date_from"]:
            datetime.strptime(filters["registration_date_from"], "%Y-%m-%d")
        if filters["registration_date_to"]:
            datetime.strptime(filters["registration_date_to"], "%Y-%m-%d")
    except ValueError:
        total_assets = count_fixed_assets(filters)
        total_pages = max((total_assets + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages)
        assets = list_fixed_assets(current_page, page_size, filters)
        return render_fixed_assets_page(
            user["email"],
            assets,
            page=current_page,
            page_size=page_size,
            total_assets=total_assets,
            filters=filters,
            message="RegistrationDate filters must be valid dates (YYYY-MM-DD).",
            message_kind="error",
        )

    if (
        filters["registration_date_from"]
        and filters["registration_date_to"]
        and filters["registration_date_from"] > filters["registration_date_to"]
    ):
        total_assets = count_fixed_assets(filters)
        total_pages = max((total_assets + page_size - 1) // page_size, 1)
        current_page = min(page, total_pages)
        assets = list_fixed_assets(current_page, page_size, filters)
        return render_fixed_assets_page(
            user["email"],
            assets,
            page=current_page,
            page_size=page_size,
            total_assets=total_assets,
            filters=filters,
            message="RegistrationDate From must be earlier than or equal to RegistrationDate To.",
            message_kind="error",
        )

    total_assets = count_fixed_assets(filters)
    total_pages = max((total_assets + page_size - 1) // page_size, 1)
    current_page = min(page, total_pages)
    assets = list_fixed_assets(current_page, page_size, filters)
    return render_fixed_assets_page(
        user["email"],
        assets,
        page=current_page,
        page_size=page_size,
        total_assets=total_assets,
        filters=filters,
    )


@app.get("/fixed-assets/id/{fixed_asset_id}", response_class=HTMLResponse)
def fixed_asset_details_page(
    fixed_asset_id: str,
    session_token: str | None = Cookie(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str = Query(default=""),
    category: str = Query(default=""),
    initial_value: str = Query(default=""),
    responsible_person: str = Query(default=""),
    registration_date_from: str = Query(default=""),
    registration_date_to: str = Query(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to access fixed asset details.")

    _, user = authenticated
    fixed_asset = get_fixed_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Fixed Asset Details",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    filters = {
        "name": name.strip(),
        "category": category.strip(),
        "initial_value": initial_value.strip(),
        "responsible_person": responsible_person.strip(),
        "registration_date_from": registration_date_from.strip(),
        "registration_date_to": registration_date_to.strip(),
    }
    return render_fixed_asset_details_page(
        user["email"],
        fixed_asset,
        page=page,
        page_size=page_size,
        filters=filters,
    )


@app.get("/fixed-assets/id/{fixed_asset_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_page(
    fixed_asset_id: str,
    session_token: str | None = Cookie(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str = Query(default=""),
    category: str = Query(default=""),
    initial_value: str = Query(default=""),
    responsible_person: str = Query(default=""),
    registration_date_from: str = Query(default=""),
    registration_date_to: str = Query(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to edit fixed assets.")

    _, user = authenticated
    fixed_asset = get_fixed_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    if not list_fixed_asset_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
        )

    filters = {
        "name": name.strip(),
        "category": category.strip(),
        "initial_value": initial_value.strip(),
        "responsible_person": responsible_person.strip(),
        "registration_date_from": registration_date_from.strip(),
        "registration_date_to": registration_date_to.strip(),
    }
    return render_edit_fixed_asset_page(
        user["email"],
        fixed_asset,
        page=page,
        page_size=page_size,
        filters=filters,
    )


@app.post("/fixed-assets/id/{fixed_asset_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_route(
    fixed_asset_id: str,
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
    category_id: str = Form(...),
    initial_value: float = Form(...),
    responsible_person: str = Form(...),
    registration_date: str = Form(...),
    page: int = Form(default=1),
    page_size: int = Form(default=20),
    name_filter: str = Form(default=""),
    category_filter: str = Form(default=""),
    initial_value_filter: str = Form(default=""),
    responsible_person_filter: str = Form(default=""),
    registration_date_from_filter: str = Form(default=""),
    registration_date_to_filter: str = Form(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to edit fixed assets.")

    _, user = authenticated
    fixed_asset = get_fixed_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    if not list_fixed_asset_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
        )

    filters = {
        "name": name_filter.strip(),
        "category": category_filter.strip(),
        "initial_value": initial_value_filter.strip(),
        "responsible_person": responsible_person_filter.strip(),
        "registration_date_from": registration_date_from_filter.strip(),
        "registration_date_to": registration_date_to_filter.strip(),
    }

    safe_page_size = max(1, min(page_size, 100))
    safe_page = max(1, page)

    if len(name) > 100 or len(responsible_person) > 100:
        return render_edit_fixed_asset_page(
            user["email"],
            fixed_asset,
            page=safe_page,
            page_size=safe_page_size,
            filters=filters,
            message="Name and ResponsiblePerson must be 100 characters or less.",
            message_kind="error",
        )

    if not category_id.strip():
        return render_edit_fixed_asset_page(
            user["email"],
            fixed_asset,
            page=safe_page,
            page_size=safe_page_size,
            filters=filters,
            message="Category is required.",
            message_kind="error",
        )

    try:
        datetime.strptime(registration_date, "%Y-%m-%d")
    except ValueError:
        return render_edit_fixed_asset_page(
            user["email"],
            fixed_asset,
            page=safe_page,
            page_size=safe_page_size,
            filters=filters,
            message="RegistrationDate must be a valid date in YYYY-MM-DD format.",
            message_kind="error",
        )

    try:
        updated = update_fixed_asset(
            fixed_asset_id=fixed_asset_id,
            name=name.strip(),
            category_id=category_id.strip(),
            initial_value=initial_value,
            responsible_person=responsible_person.strip(),
            registration_date=registration_date,
        )
    except ValueError:
        return render_edit_fixed_asset_page(
            user["email"],
            fixed_asset,
            page=safe_page,
            page_size=safe_page_size,
            filters=filters,
            message="Selected category does not exist.",
            message_kind="error",
        )
    if updated is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    return render_edit_fixed_asset_page(
        user["email"],
        updated,
        page=safe_page,
        page_size=safe_page_size,
        filters=filters,
        message="Fixed asset updated successfully.",
        message_kind="success",
    )


@app.get("/fixed-assets/add", response_class=HTMLResponse)
def add_fixed_asset_page(
    session_token: str | None = Cookie(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str = Query(default=""),
    category: str = Query(default=""),
    initial_value: str = Query(default=""),
    responsible_person: str = Query(default=""),
    registration_date_from: str = Query(default=""),
    registration_date_to: str = Query(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed assets.")

    _, user = authenticated
    filters = {
        "name": name.strip(),
        "category": category.strip(),
        "initial_value": initial_value.strip(),
        "responsible_person": responsible_person.strip(),
        "registration_date_from": registration_date_from.strip(),
        "registration_date_to": registration_date_to.strip(),
    }
    categories = list_fixed_asset_categories()
    if not categories:
        return render_page(
            "AI Hackaton Add Fixed Asset",
            "No Categories Available",
            "Create at least one category before adding fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
        )

    return render_add_fixed_asset_page(
        user["email"],
        page=page,
        page_size=page_size,
        categories=categories,
        filters=filters,
    )


@app.post("/fixed-assets/add", response_class=HTMLResponse)
def create_fixed_asset_route(
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
    category_id: str = Form(...),
    initial_value: float = Form(...),
    responsible_person: str = Form(...),
    registration_date: str = Form(...),
    page: int = Form(default=1),
    page_size: int = Form(default=20),
    name_filter: str = Form(default=""),
    category_filter: str = Form(default=""),
    initial_value_filter: str = Form(default=""),
    responsible_person_filter: str = Form(default=""),
    registration_date_from_filter: str = Form(default=""),
    registration_date_to_filter: str = Form(default=""),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed assets.")

    _, user = authenticated

    filters = {
        "name": name_filter.strip(),
        "category": category_filter.strip(),
        "initial_value": initial_value_filter.strip(),
        "responsible_person": responsible_person_filter.strip(),
        "registration_date_from": registration_date_from_filter.strip(),
        "registration_date_to": registration_date_to_filter.strip(),
    }
    categories = list_fixed_asset_categories()

    safe_page_size = max(1, min(page_size, 100))
    total_assets = count_fixed_assets(filters)
    total_pages = max((total_assets + safe_page_size - 1) // safe_page_size, 1)
    current_page = min(max(page, 1), total_pages)

    if len(name) > 100 or len(responsible_person) > 100:
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data={
                "name": name,
                "category_id": category_id,
                "initial_value": str(initial_value),
                "responsible_person": responsible_person,
                "registration_date": registration_date,
            },
            filters=filters,
            message="Name and ResponsiblePerson must be 100 characters or less.",
            message_kind="error",
        )

    if not category_id.strip():
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data={
                "name": name,
                "category_id": category_id,
                "initial_value": str(initial_value),
                "responsible_person": responsible_person,
                "registration_date": registration_date,
            },
            filters=filters,
            message="Category is required.",
            message_kind="error",
        )

    try:
        datetime.strptime(registration_date, "%Y-%m-%d")
    except ValueError:
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data={
                "name": name,
                "category_id": category_id,
                "initial_value": str(initial_value),
                "responsible_person": responsible_person,
                "registration_date": registration_date,
            },
            filters=filters,
            message="RegistrationDate must be a valid date in YYYY-MM-DD format.",
            message_kind="error",
        )

    try:
        create_fixed_asset(
            name=name.strip(),
            category_id=category_id.strip(),
            initial_value=initial_value,
            responsible_person=responsible_person.strip(),
            registration_date=registration_date,
        )
    except ValueError:
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data={
                "name": name,
                "category_id": category_id,
                "initial_value": str(initial_value),
                "responsible_person": responsible_person,
                "registration_date": registration_date,
            },
            filters=filters,
            message="Selected category does not exist.",
            message_kind="error",
        )
    updated_total_assets = count_fixed_assets(filters)
    updated_total_pages = max((updated_total_assets + safe_page_size - 1) // safe_page_size, 1)
    target_page = updated_total_pages
    return render_fixed_assets_page(
        user["email"],
        list_fixed_assets(target_page, safe_page_size, filters),
        page=target_page,
        page_size=safe_page_size,
        total_assets=updated_total_assets,
        filters=filters,
        message="Fixed asset created successfully.",
        message_kind="success",
    )


@app.get("/fixed-asset-categories", response_class=HTMLResponse)
def fixed_asset_categories_page(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    _, user = authenticated
    categories = list_fixed_asset_categories_with_usage()
    return render_fixed_asset_categories_page(user["email"], categories)


@app.post("/fixed-asset-categories", response_class=HTMLResponse)
def create_fixed_asset_category_route(
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    _, user = authenticated
    if not name.strip() or len(name.strip()) > 100:
        return render_fixed_asset_categories_page(
            user["email"],
            list_fixed_asset_categories_with_usage(),
            message="Category name is required and must be 100 characters or less.",
            message_kind="error",
        )

    try:
        create_fixed_asset_category(name.strip())
    except Exception:
        return render_fixed_asset_categories_page(
            user["email"],
            list_fixed_asset_categories_with_usage(),
            message="Unable to create category. It may already exist.",
            message_kind="error",
        )

    return render_fixed_asset_categories_page(
        user["email"],
        list_fixed_asset_categories_with_usage(),
        message="Category created successfully.",
        message_kind="success",
    )


@app.get("/fixed-asset-categories/{category_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_category_page(
    category_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    _, user = authenticated
    category = get_fixed_asset_category_by_id(category_id)
    if category is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset Category",
            "Category Not Found",
            "The requested category does not exist.",
            '<div class="links"><a href="/fixed-asset-categories">Back to categories</a></div>',
            message="Category not found.",
            message_kind="error",
        )

    return render_edit_fixed_asset_category_page(user["email"], category)


@app.post("/fixed-asset-categories/{category_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_category_route(
    category_id: str,
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    _, user = authenticated
    category = get_fixed_asset_category_by_id(category_id)
    if category is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset Category",
            "Category Not Found",
            "The requested category does not exist.",
            '<div class="links"><a href="/fixed-asset-categories">Back to categories</a></div>',
            message="Category not found.",
            message_kind="error",
        )

    if not name.strip() or len(name.strip()) > 100:
        return render_edit_fixed_asset_category_page(
            user["email"],
            category,
            message="Category name is required and must be 100 characters or less.",
            message_kind="error",
        )

    try:
        updated = update_fixed_asset_category(category_id, name.strip())
    except ValueError:
        return render_edit_fixed_asset_category_page(
            user["email"],
            category,
            message="Category name already exists.",
            message_kind="error",
        )

    if updated is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset Category",
            "Category Not Found",
            "The requested category does not exist.",
            '<div class="links"><a href="/fixed-asset-categories">Back to categories</a></div>',
            message="Category not found.",
            message_kind="error",
        )

    return render_edit_fixed_asset_category_page(
        user["email"],
        updated,
        message="Category updated successfully.",
        message_kind="success",
    )


@app.post("/fixed-asset-categories/{category_id}/delete", response_class=HTMLResponse)
def delete_fixed_asset_category_route(
    category_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    authenticated = current_user(session_token)
    if authenticated is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    _, user = authenticated
    deleted = delete_fixed_asset_category(category_id)
    if not deleted:
        return render_fixed_asset_categories_page(
            user["email"],
            list_fixed_asset_categories_with_usage(),
            message="Cannot delete category while it is used by fixed assets.",
            message_kind="error",
        )

    return render_fixed_asset_categories_page(
        user["email"],
        list_fixed_asset_categories_with_usage(),
        message="Category deleted successfully.",
        message_kind="success",
    )


@app.post("/", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if not email or not password:
        return render_login_page("Both email and password are required.", email=email)

    user = get_user_by_email(email)
    if user is None or not verify_password(password, user["password_hash"]):
        return render_login_page("Invalid email or password.", email=email)

    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="You are now logged in."),
        session_token,
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page() -> HTMLResponse:
    return render_register_page()


@app.post("/register", response_class=HTMLResponse)
def register(email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)) -> HTMLResponse:
    if not email or not password or not confirm_password:
        return render_register_page("All fields are required.", email=email)

    if password != confirm_password:
        return render_register_page("Passwords do not match.", email=email)

    if get_user_by_email(email) is not None:
        return render_register_page("That email is already registered.", email=email)

    user = create_user(email, password)
    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Account created successfully."),
        session_token,
    )
    return response


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page() -> HTMLResponse:
    return render_forgot_password_page()


@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(email: str = Form(...)) -> HTMLResponse:
    if not email:
        return render_forgot_password_page("Email is required.")

    user = get_user_by_email(email)
    if user is None:
        return render_forgot_password_page(
            "If that account exists, a reset link will be created here.",
            email=email,
        )

    token, _ = create_password_reset_token(user["id"])
    reset_link = f"/reset-password/{token}"
    content = f"""
    <div class="stack">
        <section class="panel wide">
            <h2>Reset link created</h2>
            <p>A reset link is ready for <strong>{escape(email)}</strong>.</p>
            <code>{escape(reset_link)}</code>
            <div class="links">
                <a href="{escape(reset_link)}">Open reset page</a>
                <a href="/">Back to login</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Reset Link",
        "Password reset link",
        "Open the generated link to set a new password.",
        content,
        width="520px",
        message="For local testing, the reset link is shown on screen instead of being emailed.",
        message_kind="success",
    )


@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(token: str) -> HTMLResponse:
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message="That reset link cannot be used.",
            message_kind="error",
        )

    return render_reset_password_page(token)


@app.post("/reset-password/{token}", response_class=HTMLResponse)
def reset_password(
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
) -> HTMLResponse:
    reset_token = get_password_reset_token(token)
    if reset_token is None:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message="That reset link cannot be used.",
            message_kind="error",
        )

    if not password or not confirm_password:
        return render_reset_password_page(token, "Both password fields are required.")

    if password != confirm_password:
        return render_reset_password_page(token, "Passwords do not match.")

    user_id = reset_token["user_id"]
    update_user_password(user_id, password)
    delete_sessions_for_user(user_id)
    mark_password_reset_token_used(token)

    user = get_user_by_id(user_id)
    if user is None:
        return render_login_page("Password updated, but the account could not be reloaded.")

    session_token, _ = create_session(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Password updated successfully."),
        session_token,
    )
    return response


@app.get("/logout", response_class=HTMLResponse)
def logout(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    if session_token:
        delete_session(session_token)

    response = render_login_page("You have been logged out.")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
