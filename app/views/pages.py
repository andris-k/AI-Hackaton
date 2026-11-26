from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlencode

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import config
from app.repositories import audit_repository
from app.repositories import auth_repository
from app.services import audit_view_service as audit_view
from app.repositories import fixed_assets_repository as assets_repo
from app.repositories import inventory_sessions_repository as sessions_repository
from app.repositories import locations_repository
from app.db import NO_LOCATION_FILTER

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


_WORKSPACE_NAV = (
    ("dashboard", "Dashboard", "/dashboard"),
    ("fixed-assets", "Fixed assets", "/fixed-assets"),
    ("categories", "Categories", "/fixed-asset-categories"),
    ("locations", "Locations", "/locations"),
    ("inventory", "Inventory sessions", "/inventory-sessions"),
    ("analytics", "Analytics", "/analytics"),
)
# (key, label, href, admins only)
_ADMINISTRATION_NAV = (
    ("users", "Users", "/users", False),
    ("audit", "Audit log", "/audit-log", True),
)

_HEAD = """
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{title}</title>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
            <link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
            <link rel="stylesheet" href="/static/app.css?v=10" />
"""

_BRAND = """
                <img class="brand-mark" src="/static/favicon.svg" alt="" width="28" height="28" />
                <span class="brand-text"><strong>Asset Registry</strong><span>AI Hackaton</span></span>
"""


def _nav_link(key: str, label: str, href: str, active_nav: str | None, badge: int = 0) -> str:
    if badge:
        label = f'{label} <span class="nav-badge" title="{badge} waiting for approval">{badge}</span>'
    if key == active_nav:
        return f'<a class="nav-link active" href="{href}" aria-current="page">{label}</a>'
    return f'<a class="nav-link" href="{href}">{label}</a>'


def _render_nav(current_email: str, active_nav: str | None) -> str:
    is_admin = audit_view.is_admin(current_email)
    workspace_links = "".join(_nav_link(key, label, href, active_nav) for key, label, href in _WORKSPACE_NAV)
    pending = auth_repository.pending_count() if is_admin else 0
    admin_links = "".join(
        _nav_link(key, label, href, active_nav, badge=pending if key == "users" else 0)
        for key, label, href, admins_only in _ADMINISTRATION_NAV
        if is_admin or not admins_only
    )
    links = (
        f'<p class="nav-section">Workspace</p>{workspace_links}'
        f'<p class="nav-section nav-section-divider">Administration</p>{admin_links}'
    )
    initials = escape(current_email[:2])
    email = escape(current_email)
    return f"""
            <nav class="app-nav" aria-label="Main">
                <a class="brand" href="/dashboard">{_BRAND}</a>
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
        build_note = "" if config.is_production() else "<small>Local development build</small>"
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
                {build_note}
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


def render_login_page(error: str | None = None, email: str = "", *, notice: str | None = None) -> HTMLResponse:
    content = _render_template(
        "login_page.html",
        email=email,
        show_demo_credentials=config.show_demo_credentials(),
        password_reset_available=config.password_reset_available(),
    )
    return render_page(
        "AI Hackaton Login",
        "Log in",
        "Enter your email and password to access the system.",
        content,
        message=error or notice,
        message_kind="error" if error else "info",
    )


def render_register_page(error: str | None = None, email: str = "") -> HTMLResponse:
    content = _render_template("register_page.html", email=email)
    return render_page(
        "AI Hackaton Registration",
        "Create account",
        "Request an account. An administrator approves new accounts before they can be used.",
        content,
        message=error,
        message_kind="error" if error else "info",
    )


def render_forgot_password_page(
    error: str | None = None,
    email: str = "",
    *,
    notice: str | None = None,
) -> HTMLResponse:
    available = config.password_reset_available()
    content = _render_template(
        "forgot_password_page.html",
        email=email,
        reset_available=available,
        link_on_screen=config.show_reset_link_on_screen(),
    )
    if error:
        message, message_kind = error, "error"
    elif notice:
        message, message_kind = notice, "success"
    elif not available:
        message, message_kind = (
            "Password reset by email isn't set up on this site. Ask an administrator to reset your password.",
            "info",
        )
    else:
        message, message_kind = None, "info"
    return render_page(
        "AI Hackaton Password Reset",
        "Reset password",
        "Request a reset link for an existing account.",
        content,
        message=message,
        message_kind=message_kind,
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
    from app.services import dashboard_service

    content = _render_template(
        "dashboard_page.html",
        user_email=user_email,
        **dashboard_service.build_dashboard(user_email),
    )
    return render_page(
        "AI Hackaton Dashboard",
        "Dashboard",
        "Protected workspace for authenticated users.",
        content,
        width="1200px",
        message=message,
        message_kind=message_kind,
        current_email=user_email,
        active_nav="dashboard",
    )


def render_analytics_page(current_email: str, measure: str = "value") -> HTMLResponse:
    from app.services import dashboard_service

    content = _render_template("analytics_page.html", **dashboard_service.build_analytics(measure))
    return render_page(
        "AI Hackaton Analytics",
        "Analytics",
        "The asset register in numbers.",
        content,
        width="1200px",
        current_email=current_email,
        active_nav="analytics",
    )


def render_users_page(
    current_email: str,
    users: list[object],
    email_filter: str = "",
    *,
    current_user_id: int | None = None,
    is_admin: bool = False,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    rows = [
        {
            "id": int(user["id"]),
            "email": str(user["email"]),
            "created_at": str(user["created_at"]),
            "pending": user["status"] == "pending",
            "is_admin": bool(user["is_admin"]),
            "is_self": int(user["id"]) == current_user_id,
        }
        for user in users
    ]
    table = _render_template(
        "users_page.html",
        current_email=current_email,
        email_filter=email_filter,
        is_admin=is_admin,
        # Waiting accounts are personal data and only matter to admins.
        pending=[row for row in rows if row["pending"]] if is_admin else [],
        users=[row for row in rows if not row["pending"]],
    )
    return render_page(
        "AI Hackaton Users",
        "Users",
        "List of registered users in the system.",
        table,
        width="960px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="users",
    )


def _location_choices(current_id: object = None, current_name: object = None) -> list[dict[str, str]]:
    """Locations for a dropdown. A record may keep a location that was deleted
    later, so that one is added if it is not in the list."""
    choices = [{"id": str(row["id"]), "name": str(row["name"])} for row in locations_repository.list_all()]
    if current_id and all(choice["id"] != str(current_id) for choice in choices):
        choices.append({"id": str(current_id), "name": f"{current_name or 'Unknown'} (deleted)"})
    return choices


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
    location_filter_options = [
        (NO_LOCATION_FILTER, "No location"),
        *((str(location["name"]), str(location["name"])) for location in locations_repository.list_all()),
    ]
    selected_location_filters = [
        value.strip()
        for value in str(filters.get("location", "")).split(",")
        if value.strip()
    ]
    rows = [
        {
            "id": str(asset["id"]),
            "name": str(asset["name"]),
            "category": str(asset["category"]),
            "location": str(asset["location"] or ""),
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
        "location": filters.get("location", ""),
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
    labels_query = [
        ("name", filters.get("name", "")),
        *(("category", value) for value in selected_category_filters),
        *(("location", value) for value in selected_location_filters),
        *((key, filters.get(key, "")) for key in (
            "initial_value_from", "initial_value_to", "responsible_person",
            "registration_date_from", "registration_date_to",
        )),
    ]
    content = _render_template(
        "fixed_assets_page.html",
        current_email=current_email,
        rows=rows,
        page=page,
        page_size=page_size,
        filters=filters,
        category_filter_options=category_filter_options,
        selected_category_filters=selected_category_filters,
        location_filter_options=location_filter_options,
        selected_location_filters=selected_location_filters,
        total_assets=total_assets,
        total_pages=total_pages,
        start_row=start_row,
        end_row=end_row,
        add_asset_href=f"/fixed-assets/add?{urlencode(add_asset_query)}",
        labels_href=f"/fixed-assets/labels.pdf?{urlencode([(k, v) for k, v in labels_query if v])}",
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
    count_sessions: list[object] | None = None,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    back_query = {
        "page": str(page),
        "page_size": str(page_size),
        "name": filters.get("name", ""),
        "category": filters.get("category", ""),
        "location": filters.get("location", ""),
        "initial_value_from": filters.get("initial_value_from", ""),
        "initial_value_to": filters.get("initial_value_to", ""),
        "responsible_person": filters.get("responsible_person", ""),
        "registration_date_from": filters.get("registration_date_from", ""),
        "registration_date_to": filters.get("registration_date_to", ""),
    }

    content = _render_template(
        "fixed_asset_details_page.html",
        **_history(current_email, "asset", str(fixed_asset["id"])),
        current_email=current_email,
        fixed_asset={
            "id": str(fixed_asset["id"]),
            "name": str(fixed_asset["name"]),
            "category": str(fixed_asset["category"]),
            "location": str(fixed_asset["location"] or ""),
            "quantity": str(fixed_asset["quantity"]),
            "initial_value": "{:.2f}".format(float(fixed_asset["initial_value"])),
            "responsible_person": str(fixed_asset["responsible_person"]),
            "registration_date": str(fixed_asset["registration_date"]),
            "image_url": _fixed_asset_image_url(fixed_asset["image_path"]),
            "deleted_at": fixed_asset["deleted_at"],
        },
        page=page,
        page_size=page_size,
        filters=filters,
        delete_action=f"/fixed-assets/id/{fixed_asset['id']}/delete",
        label_href=f"/fixed-assets/id/{fixed_asset['id']}/label.pdf",
        count_sessions=[
            {
                "id": str(row["id"]),
                "label": f"{row['date_from']} – {row['date_to']} · {row['responsible_person']}",
                "location": f"Counting at {row['location']}" if row["location"] else "No active location",
                "quantity": row["quantity"],
            }
            for row in (count_sessions or [])
        ],
        edit_href=f"/fixed-assets/id/{fixed_asset['id']}/edit?{urlencode(back_query)}",
        back_href=f"/fixed-assets?{urlencode(back_query)}",
    )
    return render_page(
        "AI Hackaton Fixed Asset Details",
        "Fixed Asset Details",
        "Detailed view of a fixed asset.",
        content,
        width="860px",
        message=message,
        message_kind=message_kind,
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
        "location": filters.get("location", ""),
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
        locations=_location_choices(fixed_asset["location_id"], fixed_asset["location"]),
        selected_location_id=str(fixed_asset["location_id"] or ""),
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
        "location": filters.get("location", ""),
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
        locations=_location_choices(),
        selected_location_id=form_data.get("location_id", ""),
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


_IMPORT_PREVIEW_ROWS = 100


def render_fixed_asset_import_page(
    current_email: str,
    *,
    preview: object | None = None,
    token: str = "",
    filename: str = "",
    imported: dict[str, object] | None = None,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    """Upload form; or the preview of an uploaded file (rows with errors first);
    or the result after importing."""
    shown_rows: list[object] = []
    if preview is not None:
        rows = list(preview.rows)
        problem_rows = [row for row in rows if row.errors]
        shown_rows = (problem_rows or rows)[:_IMPORT_PREVIEW_ROWS]
    content = _render_template(
        "fixed_asset_import_page.html",
        preview=preview,
        shown_rows=shown_rows,
        token=token,
        filename=filename,
        imported=imported,
    )
    return render_page(
        "AI Hackaton Import Fixed Assets",
        "Import fixed assets",
        "Add many fixed assets from a CSV file.",
        content,
        width="1100px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="fixed-assets",
    )


def render_locations_page(
    current_email: str,
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    content = _render_template(
        "locations_page.html",
        locations=[
            {
                "id": str(location["id"]),
                "name": str(location["name"]),
                "assets_count": int(location["assets_count"]),
                "sessions_count": int(location["sessions_count"]),
                "assets_href": f"/fixed-assets?{urlencode({'location': str(location['name'])})}",
            }
            for location in locations_repository.list_with_usage()
        ],
    )
    return render_page(
        "AI Hackaton Locations",
        "Locations",
        "Create and manage asset locations.",
        content,
        width="980px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="locations",
    )


def render_edit_location_page(
    current_email: str,
    location: object,
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    content = _render_template(
        "location_edit_page.html",
        location={"id": str(location["id"]), "name": str(location["name"])},
    )
    return render_page(
        "AI Hackaton Edit Location",
        "Edit Location",
        "Update location name.",
        content,
        width="760px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="locations",
    )


# ---------------------------------------------------------------------------
# Inventory Sessions
# ---------------------------------------------------------------------------

def _short_time(value: object) -> str:
    """'2026-11-25T09:15:00.123+00:00' -> '2026-11-25 09:15'."""
    text = str(value or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else text


def session_locations(session_id: str) -> dict[str, object]:
    """Where each asset was counted, and the session's location history."""
    counted_at: dict[str, list[str]] = {}
    for row in sessions_repository.counts(session_id):
        if int(row["quantity"]) > 0:
            counted_at.setdefault(str(row["fixed_asset_id"]), []).append(
                f"{row['location'] or 'No location'}: {row['quantity']}"
            )
    return {
        "counted_at": {asset_id: " · ".join(parts) for asset_id, parts in counted_at.items()},
        "location_history": [
            {
                "time": _short_time(row["activated_at"]),
                "location": row["location"] or "No location",
                "by": row["activated_by_email"] or "",
            }
            for row in sessions_repository.location_history(session_id)
        ],
    }

def render_inventory_sessions_page(
    current_email: str,
    sessions: list[object],
    statuses: list[str],
    filters: dict[str, str],
    summary: dict[str, object] | None = None,
    *,
    locations: list[dict[str, str]] | None = None,
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
        locations=locations or [],
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
    locations: list[dict[str, str]] | None = None,
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
        locations=locations or [],
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
        **_history(current_email, "inventory_session", str(inv_session["id"])),
        **session_locations(str(inv_session["id"])),
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


def render_inventory_session_results_page(
    current_email: str,
    inv_session: object,
    *,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    """Results of a Completed or Cancelled session."""
    from app.services import session_results_service as results

    ended = inv_session["completed_at"] if inv_session["status"] == "Completed" else inv_session["cancelled_at"]
    content = _render_template(
        "inventory_session_results_page.html",
        **_history(current_email, "inventory_session", str(inv_session["id"])),
        **results.build_results(inv_session),
        inv_session=inv_session,
        ended_at=_short_time(ended),
        is_admin=audit_view.is_admin(current_email),
    )
    return render_page(
        "AI Hackaton Inventory Results",
        "Inventory results",
        "Results of an inventory session.",
        content,
        width="1200px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="inventory",
    )


def render_count_row(row: dict[str, object], session_id: str) -> str:
    """One row of the counting workspace, as sent back after each count."""
    return _render_template("inventory_count_row.html", r=row, session_id=session_id)


def render_inventory_session_count_page(
    current_email: str,
    inv_session: object,
    *,
    locations: list[dict[str, str]] | None = None,
    selected_tab: str = "all",
    details_open: bool = False,
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    """The counting workspace of an Active session."""
    from app.services import counting_workspace_service as workspace

    session_id = str(inv_session["id"])
    rows = workspace.build_rows(inv_session)
    counts = workspace.summary(rows)
    content = _render_template(
        "inventory_session_count_page.html",
        inv_session=inv_session,
        session_id=session_id,
        rows=rows,
        summary=counts,
        tabs=workspace.tabs(counts),
        selected_tab=selected_tab if selected_tab in {key for key, _ in workspace.TABS} else "all",
        locations=locations or [],
        recent=workspace.recent_counts(session_id),
        location_history=session_locations(session_id)["location_history"],
        details_open=details_open,
    )
    return render_page(
        "AI Hackaton Count Inventory",
        "Count inventory",
        "Count the assets of an inventory session.",
        content,
        width="1200px",
        message=message,
        message_kind=message_kind,
        current_email=current_email,
        active_nav="inventory",
    )


def render_inventory_session_finish_page(
    current_email: str,
    inv_session: object,
    *,
    completion_reason: str = "",
    message: str | None = None,
    message_kind: str = "info",
) -> HTMLResponse:
    """Review before completing: what is not counted yet, the differences, the locations used."""
    from app.services import counting_workspace_service as workspace

    content = _render_template(
        "inventory_session_finish_page.html",
        inv_session=inv_session,
        completion_reason=completion_reason,
        location_history=session_locations(str(inv_session["id"]))["location_history"],
        **workspace.build_review(inv_session),
    )
    return render_page(
        "AI Hackaton Finish Counting",
        "Finish counting",
        "Review the results before completing the session.",
        content,
        width="1100px",
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
    locations: list[dict[str, str]] | None = None,
    error: str | None = None,
    prefill: dict[str, str] | None = None,
) -> HTMLResponse:
    content = _render_template(
        "inventory_session_edit_page.html",
        locations=locations or [],
        location_history=session_locations(str(inv_session["id"]))["location_history"],
        **_history(current_email, "inventory_session", str(inv_session["id"])),
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



# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _history(current_email: str, entity_type: str, entity_id: str) -> dict[str, object]:
    """History rows for one record, only for administrators (None hides the section)."""
    if not audit_view.is_admin(current_email):
        return {"history": None, "history_link": ""}
    rows = audit_repository.list_entity_events(entity_type, entity_id, limit=20)
    return {
        "history": [audit_view.present(row) for row in rows],
        "history_link": f"/audit-log?{urlencode({'entity_type': entity_type, 'entity_id': entity_id})}",
    }


def render_audit_log_page(current_email: str, rows: list[dict[str, object]], **context: object) -> HTMLResponse:
    content = _render_template("audit_log_page.html", rows=rows, **context)
    return render_page(
        "AI Hackaton Audit Log",
        "Audit log",
        "Who did what.",
        content,
        width="1320px",
        current_email=current_email,
        active_nav="audit",
    )
