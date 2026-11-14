from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Query
from fastapi.responses import HTMLResponse

from app.repositories import audit_repository
from app.services import audit_view_service as audit_view
from app.services import auth_service
from app.views.pages import render_audit_log_page, render_login_page, render_page

router = APIRouter()
PAGE_SIZE = 50


@router.get("/audit-log", response_class=HTMLResponse)
def audit_log_page(
    session_token: str | None = Cookie(default=None),
    area: str = Query(default=""),
    event: str = Query(default=""),
    actor: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    entity_type: str = Query(default=""),
    entity_id: str = Query(default=""),
    page: int = Query(default=1),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to view the audit log.")
    if not audit_view.is_admin(str(user["email"])):
        response = render_page(
            "AI Hackaton Audit Log",
            "Audit log",
            "Only administrators can view the audit log.",
            '<p style="margin:0">The audit log contains personal data, so it is limited to administrators. '
            'Ask an administrator if you need information from it.</p>',
            current_email=user["email"],
        )
        response.status_code = 403
        return response

    filters = {
        "area": area if area in audit_view.AREAS else "",
        "event": event if event in audit_view.EVENT_LABELS else "",
        "actor": actor.strip(),
        "date_from": date_from.strip(),
        "date_to": date_to.strip(),
        "entity_type": entity_type if entity_type in {"asset", "category", "inventory_session", "user"} else "",
        "entity_id": entity_id.strip()[:64],
    }
    total = audit_repository.count_events(filters)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), total_pages)
    rows = audit_repository.list_events(filters, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)

    labels = audit_view.session_labels(rows)

    def page_href(target: int) -> str:
        query = {key: value for key, value in filters.items() if value}
        query["page"] = str(target)
        return f"/audit-log?{urlencode(query)}"

    return render_audit_log_page(
        user["email"],
        [audit_view.present(row, labels) for row in rows],
        filters=filters,
        event_choices=audit_view.event_choices(),
        areas=audit_view.AREAS,
        page=page,
        total_pages=total_pages,
        total=total,
        start_row=(page - 1) * PAGE_SIZE + 1 if total else 0,
        end_row=min(page * PAGE_SIZE, total),
        previous_href=page_href(page - 1) if page > 1 else None,
        next_href=page_href(page + 1) if page < total_pages else None,
    )
