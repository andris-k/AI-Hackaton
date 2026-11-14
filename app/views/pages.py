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


def _fixed_asset_image_url(image_path: object) -> str | None:
    raw_value = str(image_path or "").strip()
    if not raw_value:
        return None
    return f"/uploads/{raw_value}"


_NAV_ITEMS = (
    ("dashboard", "Dashboard", "/dashboard"),
    ("fixed-assets", "Fixed assets", "/fixed-assets"),
    ("categories", "Categories", "/fixed-asset-categories"),
    ("inventory", "Inventory sessions", "/inventory-sessions"),
    ("users", "Users", "/users"),
)

_HEAD = """
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{title}</title>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
            <link rel="stylesheet" href="/static/app.css?v=1" />
"""

_BRAND = """
                <span class="brand-mark" aria-hidden="true">FA</span>
                <span class="brand-text"><strong>Asset Registry</strong><span>AI Hackaton</span></span>
"""


def _render_nav(current_email: str, active_nav: str | None) -> str:
    link_parts = []
    for key, label, href in _NAV_ITEMS:
        if key == active_nav:
            link_parts.append(f'<a class="nav-link active" href="{href}" aria-current="page">{label}</a>')
        else:
            link_parts.append(f'<a class="nav-link" href="{href}">{label}</a>')
    links = "".join(link_parts)
    initials = escape(current_email[:2])
    email = escape(current_email)
    return f"""
            <nav class="app-nav" aria-label="Main">
                <a class="brand" href="/dashboard">{_BRAND}</a>
                <p class="nav-section">Workspace</p>
                {links}
                <span class="nav-spacer"></span>
                <div class="nav-user">
                    <span class="nav-avatar" aria-hidden="true">{initials}</span>
                    <div class="nav-user-text">
                        <span title="{email}">{email}</span>
                        <a href="/logout">Log out</a>
                    </div>
                </div>
            </nav>
    """


def render_page(
    page_title: str,
    heading: str,
    subtitle: str,
    content: str,
    *,
    width: str = "440px",
    message: str | None = None,
    message_kind: str = "info",
    current_email: str | None = None,
    active_nav: str | None = None,
) -> HTMLResponse:
    """Render a full HTML page.

    Signed-in pages (``current_email`` given) use the app shell with the sidebar;
    the template content supplies its own page header. Other pages use the
    split-screen auth layout with ``heading`` and ``subtitle`` above the content.
    """
    message_block = f'<p class="message {message_kind}">{escape(message)}</p>' if message else ""
    head = _HEAD.format(title=escape(page_title))

    if current_email:
        if 'class="page-header"' not in content:
            content = f"""
                <div class="page-header">
                    <div>
                        <h2>{escape(heading)}</h2>
                        <p class="page-context">{escape(subtitle)}</p>
                    </div>
                </div>
                <section class="section-card">{content}</section>
            """
        body = f"""
        <div class="app-shell">
            {_render_nav(current_email, active_nav)}
            <main class="app-main">
                <div class="app-content" style="max-width: max({width}, 1080px);">
                    {message_block}
                    {content}
                </div>
            </main>
        </div>
        """
    else:
        body = f"""
        <div class="auth-shell">
            <aside class="auth-aside">
                <a class="brand" href="/">{_BRAND}</a>
                <div>
                    <h2>Every asset, its owner and its value in one register.</h2>
                    <p>Register fixed assets, organise them by category and run inventory sessions to check what is really on hand.</p>
                    <ul>
                        <li>Fixed asset register with images</li>
                        <li>Categories and responsible persons</li>
                        <li>Inventory sessions with counted vs expected quantities</li>
                    </ul>
                </div>
                <small>Local development build</small>
            </aside>
            <main class="auth-main">
                <div class="auth-card" style="--card-width: max({width}, 400px);">
                    <p class="eyebrow">Asset Registry</p>
                    <h1>{escape(heading)}</h1>
                    <p class="subtitle">{escape(subtitle)}</p>
                    {message_block}
                    {content}
                </div>
            </main>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
    <head>{head}</head>
    <body>{body}</body>
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
        current_email=user_email,
        active_nav="dashboard",
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
        current_email=current_email,
        active_nav="users",
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
            "quantity": str(asset["quantity"]),
            "initial_value": "{:.2f}".format(float(asset["initial_value"])),
            "responsible_person": str(asset["responsible_person"]),
            "registration_date": str(asset["registration_date"]),
            "image_url": _fixed_asset_image_url(asset["image_path"]),
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
        width="1320px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="fixed-assets",
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
            "quantity": str(fixed_asset["quantity"]),
            "initial_value": "{:.2f}".format(float(fixed_asset["initial_value"])),
            "responsible_person": str(fixed_asset["responsible_person"]),
            "registration_date": str(fixed_asset["registration_date"]),
            "image_url": _fixed_asset_image_url(fixed_asset["image_path"]),
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
        current_email=current_email,
        active_nav="fixed-assets",
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
            "quantity": str(fixed_asset["quantity"]),
            "initial_value": "{:.2f}".format(float(fixed_asset["initial_value"])),
            "responsible_person": str(fixed_asset["responsible_person"]),
            "registration_date": str(fixed_asset["registration_date"]),
            "image_url": _fixed_asset_image_url(fixed_asset["image_path"]),
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
        current_email=current_email,
        active_nav="fixed-assets",
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
            "quantity": form_data.get("quantity", "1"),
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
        current_email=current_email,
        active_nav="fixed-assets",
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
        current_email=current_email,
        active_nav="categories",
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
        current_email=current_email,
        active_nav="categories",
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
        current_email=current_email,
        active_nav="inventory",
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
        current_email=current_email,
        active_nav="inventory",
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
        current_email=current_email,
        active_nav="inventory",
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
        width="1120px",
        message=error,
        message_kind="error" if error else "info",
        current_email=current_email,
        active_nav="inventory",
    )

