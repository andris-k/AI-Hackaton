from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.repositories import fixed_assets_repository as assets_repo

_TEMPLATES_PATH = Path(__file__).resolve().parent / "templates"
_TEMPLATE_ENV = Environment(
    loader=FileSystemLoader(_TEMPLATES_PATH),
    autoescape=select_autoescape(default_for_string=True, default=True),
)


def _render_template(template_name: str, **context: object) -> str:
    template = _TEMPLATE_ENV.get_template(template_name)
    return template.render(**context)


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
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
            <link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:wght@600;700&display=swap" rel="stylesheet" />
            <style>
                :root {{
                    color-scheme: light;
                    font-family: "Source Sans 3", "IBM Plex Sans", "Segoe UI", Arial, sans-serif;
                    --bg: radial-gradient(1200px 640px at 15% -10%, #f8f2e7 0%, #f5efe4 58%, #ede7dd 100%);
                    --surface: #ffffff;
                    --surface-alt: #faf7f1;
                    --text: #1f2933;
                    --muted: #5d6672;
                    --accent: #26476d;
                    --accent-hover: #1f3c5d;
                    --border: #d9cfbf;
                    --success: #16685d;
                    --error: #9f2f2a;
                    --info: #2f4f7f;
                    --ring: rgba(38, 71, 109, 0.2);
                    --shadow: 0 14px 28px rgba(54, 39, 23, 0.1);
                    --table-head-bg: #f5eee2;
                    --table-row-alt: #fcfaf6;
                }}

                * {{ box-sizing: border-box; }}

                body {{
                    margin: 0;
                    min-height: 100vh;
                    display: block;
                    background: var(--bg);
                    color: var(--text);
                    padding: 16px;
                }}

                .card {{
                    width: min(100%, {width});
                    margin: 0 auto;
                    background: var(--surface);
                    border: 1px solid var(--border);
                    border-radius: 14px;
                    box-shadow: var(--shadow);
                    padding: 22px;
                }}

                .eyebrow {{
                    margin: 0 0 9px;
                    color: var(--accent);
                    font-size: 0.7rem;
                    font-weight: 700;
                    letter-spacing: 0.14em;
                    text-transform: uppercase;
                }}

                h1 {{
                    margin: 0 0 6px;
                    font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
                    font-size: 1.6rem;
                    line-height: 1.2;
                    font-weight: 700;
                }}

                p.subtitle {{
                    margin: 0 0 16px;
                    color: var(--muted);
                    line-height: 1.5;
                    font-size: 0.97rem;
                }}

                .message {{
                    margin: 0 0 12px;
                    padding: 9px 12px;
                    border-radius: 10px;
                    border: 1px solid transparent;
                    font-size: 0.88rem;
                }}

                .message.info {{ background: #eef2fb; color: var(--info); border-color: #ccd9f0; }}
                .message.success {{ background: #edf8f4; color: var(--success); border-color: #b6ddd3; }}
                .message.error {{ background: #fdf0ef; color: var(--error); border-color: #efc3c0; }}

                label {{
                    display: block;
                    margin: 0 0 5px;
                    font-size: 0.8rem;
                    font-weight: 700;
                    letter-spacing: 0.015em;
                    color: #334155;
                }}

                .field {{ margin-bottom: 12px; }}

                input, select {{
                    width: 100%;
                    border: 1px solid var(--border);
                    border-radius: 10px;
                    padding: 10px 11px;
                    font-size: 0.9rem;
                    background: var(--surface-alt);
                    outline: none;
                    transition: border-color 0.15s ease, box-shadow 0.15s ease;
                }}

                input:focus, select:focus {{
                    border-color: var(--accent);
                    box-shadow: 0 0 0 3px var(--ring);
                }}

                button {{
                    width: 100%;
                    border: 1px solid var(--accent);
                    border-radius: 10px;
                    padding: 10px 12px;
                    background: var(--accent);
                    color: white;
                    font-size: 0.88rem;
                    font-weight: 700;
                    cursor: pointer;
                    transition: background-color 0.15s ease, border-color 0.15s ease;
                }}

                button:hover {{
                    background: var(--accent-hover);
                    border-color: var(--accent-hover);
                }}

                .links {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 10px;
                    margin-top: 12px;
                }}

                .links a {{
                    color: var(--accent);
                    font-size: 0.87rem;
                    font-weight: 700;
                    text-decoration: none;
                }}

                .links a:hover {{
                    color: var(--accent-hover);
                    text-decoration: underline;
                }}

                .small {{
                    margin-top: 10px;
                    color: var(--muted);
                    font-size: 0.81rem;
                    line-height: 1.45;
                }}

                .stack {{ display: grid; gap: 12px; }}

                .panel {{
                    border: 1px solid var(--border);
                    border-radius: 12px;
                    padding: 14px;
                    background: var(--surface);
                }}

                .panel h2 {{
                    margin: 0 0 6px;
                    font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
                    font-size: 1.08rem;
                    font-weight: 600;
                }}

                code {{
                    display: block;
                    margin-top: 8px;
                    padding: 9px 11px;
                    border: 1px solid var(--border);
                    border-radius: 10px;
                    background: var(--surface-alt);
                    font-size: 0.8rem;
                    overflow-wrap: anywhere;
                }}

                table {{
                    width: 100%;
                    border-collapse: collapse;
                    border: 1px solid var(--border);
                    background: var(--surface);
                }}

                th, td {{
                    padding: 9px 9px;
                    text-align: left;
                    border-bottom: 1px solid var(--border);
                    font-size: 0.85rem;
                }}

                th {{
                    background: var(--table-head-bg);
                    font-weight: 700;
                    color: #273548;
                }}

                tr:last-child td {{ border-bottom: 0; }}

                .dashboard-grid {{
                    display: grid;
                    gap: 10px;
                }}

                @media (min-width: 900px) {{
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
    content = _render_template("login_page.html", email=email)
    return render_page(
        "AI Hackaton Login",
        "Log in",
        "Enter your email and password to access the system.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_register_page(error: str | None = None, email: str = "") -> HTMLResponse:
    content = _render_template("register_page.html", email=email)
    return render_page(
        "AI Hackaton Registration",
        "Create account",
        "Register a new user to access the dashboard.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_forgot_password_page(error: str | None = None, email: str = "") -> HTMLResponse:
    content = _render_template("forgot_password_page.html", email=email)
    return render_page(
        "AI Hackaton Password Reset",
        "Reset password",
        "Request a reset link for an existing account.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_reset_password_page(token: str, error: str | None = None) -> HTMLResponse:
    content = _render_template("reset_password_page.html", token=token)
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
    content = _render_template(
        "dashboard_page.html",
        user_email=user_email,
        session_token=session_token,
    )
    return render_page(
        "AI Hackaton Dashboard",
        "Dashboard",
        "Protected workspace for authenticated users.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def render_users_page(current_email: str, users: list[object], email_filter: str = "") -> HTMLResponse:
    table = _render_template(
        "users_page.html",
        current_email=current_email,
        email_filter=email_filter,
        users=[
            {
                "id": str(user["id"]),
                "email": str(user["email"]),
                "created_at": str(user["created_at"]),
            }
            for user in users
        ],
    )
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
    filters: dict[str, object],
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    category_filter_options = [str(category["name"]) for category in assets_repo.list_categories()]
    selected_category_filters = [
        value.strip()
        for value in str(filters.get("category", "")).split(",")
        if value.strip()
    ]
    rows = [
        {
            "id": str(asset["id"]),
            "name": str(asset["name"]),
            "category": str(asset["category"]),
            "initial_value": "{:.2f}".format(float(asset["initial_value"])),
            "responsible_person": str(asset["responsible_person"]),
            "registration_date": str(asset["registration_date"]),
        }
        for asset in fixed_assets
    ]
    total_pages = max((total_assets + page_size - 1) // page_size, 1)
    previous_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages
    start_row = (page - 1) * page_size + 1 if total_assets > 0 else 0
    end_row = min(page * page_size, total_assets)

    base_query = {
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value_from": filters.get("initial_value_from", ""),
        "initial_value_to": filters.get("initial_value_to", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    def page_link(target_page: int) -> str:
        query = {**base_query, "page": str(target_page)}
        return f"/fixed-assets?{urlencode(query)}"

    add_asset_query = {**base_query, "page": str(page)}
    content = _render_template(
        "fixed_assets_page.html",
        current_email=current_email,
        rows=rows,
        page=page,
        page_size=page_size,
        filters=filters,
        category_filter_options=category_filter_options,
        selected_category_filters=selected_category_filters,
        total_assets=total_assets,
        total_pages=total_pages,
        start_row=start_row,
        end_row=end_row,
        add_asset_href=f"/fixed-assets/add?{urlencode(add_asset_query)}",
        clear_filters_href=f"/fixed-assets?page=1&page_size={page_size}",
        previous_page_href=page_link(previous_page) if page > 1 else None,
        next_page_href=page_link(next_page) if page < total_pages else None,
    )
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
    filters: dict[str, object],
) -> HTMLResponse:
    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value_from": filters.get("initial_value_from", ""),
        "initial_value_to": filters.get("initial_value_to", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = _render_template(
        "fixed_asset_details_page.html",
        current_email=current_email,
        fixed_asset={
            "id": str(fixed_asset["id"]),
            "name": str(fixed_asset["name"]),
            "category": str(fixed_asset["category"]),
            "initial_value": "{:.2f}".format(float(fixed_asset["initial_value"])),
            "responsible_person": str(fixed_asset["responsible_person"]),
            "registration_date": str(fixed_asset["registration_date"]),
        },
        page=page,
        page_size=page_size,
        filters=filters,
        delete_action=f"/fixed-assets/id/{fixed_asset['id']}/delete",
        edit_href=f"/fixed-assets/id/{fixed_asset['id']}/edit?{urlencode(back_query)}",
        back_href=f"/fixed-assets?{urlencode(back_query)}",
    )
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
    categories = assets_repo.list_categories()
    selected_category_id = (
        str(fixed_asset["category_id"])
        if "category_id" in fixed_asset.keys() and fixed_asset["category_id"]
        else ""
    )

    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value_from": filters.get("initial_value_from", ""),
        "initial_value_to": filters.get("initial_value_to", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = _render_template(
        "fixed_asset_edit_page.html",
        current_email=current_email,
        fixed_asset={
            "id": str(fixed_asset["id"]),
            "name": str(fixed_asset["name"]),
            "initial_value": "{:.2f}".format(float(fixed_asset["initial_value"])),
            "responsible_person": str(fixed_asset["responsible_person"]),
            "registration_date": str(fixed_asset["registration_date"]),
        },
        page=page,
        page_size=page_size,
        filters=filters,
        categories=[{"id": str(category["id"]), "name": str(category["name"])} for category in categories],
        selected_category_id=selected_category_id,
        details_href=f"/fixed-assets/id/{fixed_asset['id']}?{urlencode(back_query)}",
        back_href=f"/fixed-assets?{urlencode(back_query)}",
    )
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
    form_data = form_data or {}
    selected_category_id = form_data.get("category_id", "")

    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "initial_value_from": filters.get("initial_value_from", ""),
        "initial_value_to": filters.get("initial_value_to", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = _render_template(
        "fixed_asset_add_page.html",
        current_email=current_email,
        page=page,
        page_size=page_size,
        filters=filters,
        form_data={
            "name": form_data.get("name", ""),
            "category_id": form_data.get("category_id", ""),
            "initial_value": form_data.get("initial_value", ""),
            "responsible_person": form_data.get("responsible_person", ""),
            "registration_date": form_data.get("registration_date", ""),
        },
        categories=[{"id": str(category["id"]), "name": str(category["name"])} for category in categories],
        selected_category_id=selected_category_id,
        back_href=f"/fixed-assets?{urlencode(back_query)}",
    )
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
    content = _render_template(
        "fixed_asset_categories_page.html",
        current_email=current_email,
        categories=[
            {
                "id": str(category["id"]),
                "name": str(category["name"]),
                "assets_count": str(category["assets_count"]),
            }
            for category in categories
        ],
    )
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
    content = _render_template(
        "fixed_asset_category_edit_page.html",
        current_email=current_email,
        category={
            "id": str(category["id"]),
            "name": str(category["name"]),
        },
    )
    return render_page(
        "AI Hackaton Edit Fixed Asset Category",
        "Edit Fixed Asset Category",
        "Update fixed asset category name.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


# ---------------------------------------------------------------------------
# Inventory Sessions
# ---------------------------------------------------------------------------

def render_inventory_sessions_page(
    current_email: str,
    sessions: list[object],
    statuses: list[str],
    filters: dict[str, str],
    summary: dict[str, object] | None = None,
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    content = _render_template(
        "inventory_sessions_page.html",
        current_email=current_email,
        sessions=sessions,
        statuses=statuses,
        filters=filters,
        summary=summary,
    )
    return render_page(
        "AI Hackaton Inventory Sessions",
        "Inventory Sessions",
        "Manage inventory sessions.",
        content,
        width="1100px",
        message=message,
        message_kind=message_kind,
    )


def render_add_inventory_session_page(
    current_email: str,
    fixed_assets: list[object],
    linked_asset_rows: list[dict[str, str]],
    *,
    error: str | None = None,
    prefill: dict[str, str] | None = None,
) -> HTMLResponse:
    content = _render_template(
        "inventory_session_add_page.html",
        current_email=current_email,
        error=error,
        prefill=prefill,
        fixed_assets=fixed_assets,
        linked_asset_rows=linked_asset_rows,
    )
    return render_page(
        "AI Hackaton New Inventory Session",
        "New Inventory Session",
        "Create a new inventory session.",
        content,
        width="760px",
    )


def render_inventory_session_details_page(
    current_email: str,
    inv_session: object,
    linked_assets: list[object],
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    content = _render_template(
        "inventory_session_details_page.html",
        current_email=current_email,
        inv_session=inv_session,
        linked_assets=linked_assets,
    )
    return render_page(
        "AI Hackaton Inventory Session",
        "Inventory Session",
        "View inventory session details.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
    )


def render_edit_inventory_session_page(
    current_email: str,
    inv_session: object,
    statuses: list[str],
    fixed_assets: list[object],
    linked_asset_rows: list[dict[str, str]],
    is_read_only: bool,
    is_admin_user: bool = False,
    *,
    error: str | None = None,
    prefill: dict[str, str] | None = None,
) -> HTMLResponse:
    content = _render_template(
        "inventory_session_edit_page.html",
        current_email=current_email,
        inv_session=inv_session,
        statuses=statuses,
        fixed_assets=fixed_assets,
        linked_asset_rows=linked_asset_rows,
        is_read_only=is_read_only,
        is_admin_user=is_admin_user,
        error=error,
        prefill=prefill,
    )
    return render_page(
        "AI Hackaton Edit Inventory Session",
        "Edit Inventory Session",
        "Update inventory session.",
        content,
        width="760px",
        message=error,
        message_kind="error" if error else "info",
    )

