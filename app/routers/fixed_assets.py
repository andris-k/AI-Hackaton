from __future__ import annotations

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse

from app.repositories import fixed_assets_repository as assets_repo
from app.services import auth_service
from app.services import fixed_assets_service as assets_service
from app.views.pages import (
    render_add_fixed_asset_page,
    render_edit_fixed_asset_page,
    render_fixed_asset_details_page,
    render_fixed_assets_page,
    render_login_page,
    render_page,
)

router = APIRouter()


@router.get("/fixed-assets", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access fixed assets.")

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date_from=registration_date_from,
        registration_date_to=registration_date_to,
    )

    validation_error = assets_service.validate_list_filters(filters)
    total_assets = assets_repo.count_assets(filters)
    current_page, safe_page_size, _ = assets_service.normalize_paging(page, page_size, total_assets)
    assets = assets_repo.list_assets(current_page, safe_page_size, filters)
    if validation_error:
        return render_fixed_assets_page(
            user["email"],
            assets,
            page=current_page,
            page_size=safe_page_size,
            total_assets=total_assets,
            filters=filters,
            message=validation_error,
            message_kind="error",
        )

    return render_fixed_assets_page(
        user["email"],
        assets,
        page=current_page,
        page_size=safe_page_size,
        total_assets=total_assets,
        filters=filters,
    )


@router.get("/fixed-assets/id/{fixed_asset_id}", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access fixed asset details.")

    fixed_asset = assets_repo.get_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Fixed Asset Details",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date_from=registration_date_from,
        registration_date_to=registration_date_to,
    )
    return render_fixed_asset_details_page(
        user["email"],
        fixed_asset,
        page=page,
        page_size=page_size,
        filters=filters,
    )


@router.get("/fixed-assets/id/{fixed_asset_id}/edit", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit fixed assets.")

    fixed_asset = assets_repo.get_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    if not assets_repo.list_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
        )

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date_from=registration_date_from,
        registration_date_to=registration_date_to,
    )
    return render_edit_fixed_asset_page(
        user["email"],
        fixed_asset,
        page=page,
        page_size=page_size,
        filters=filters,
    )


@router.post("/fixed-assets/id/{fixed_asset_id}/edit", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit fixed assets.")

    fixed_asset = assets_repo.get_asset_by_id(fixed_asset_id)
    if fixed_asset is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
        )

    if not assets_repo.list_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
        )

    filters = assets_service.build_filters(
        name=name_filter,
        category=category_filter,
        initial_value=initial_value_filter,
        responsible_person=responsible_person_filter,
        registration_date_from=registration_date_from_filter,
        registration_date_to=registration_date_to_filter,
    )
    safe_page = max(1, page)
    _, safe_page_size, _ = assets_service.normalize_paging(safe_page, page_size, 1)

    form_error = assets_service.validate_asset_form(
        name=name,
        category_id=category_id,
        responsible_person=responsible_person,
        registration_date=registration_date,
    )
    if form_error:
        return render_edit_fixed_asset_page(
            user["email"],
            fixed_asset,
            page=safe_page,
            page_size=safe_page_size,
            filters=filters,
            message=form_error,
            message_kind="error",
        )

    try:
        updated = assets_repo.update_asset(
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


@router.get("/fixed-assets/add", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed assets.")

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value=initial_value,
        responsible_person=responsible_person,
        registration_date_from=registration_date_from,
        registration_date_to=registration_date_to,
    )
    categories = assets_repo.list_categories()
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


@router.post("/fixed-assets/add", response_class=HTMLResponse)
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
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed assets.")

    filters = assets_service.build_filters(
        name=name_filter,
        category=category_filter,
        initial_value=initial_value_filter,
        responsible_person=responsible_person_filter,
        registration_date_from=registration_date_from_filter,
        registration_date_to=registration_date_to_filter,
    )
    categories = assets_repo.list_categories()

    total_assets = assets_repo.count_assets(filters)
    current_page, safe_page_size, _ = assets_service.normalize_paging(page, page_size, total_assets)

    form_error = assets_service.validate_asset_form(
        name=name,
        category_id=category_id,
        responsible_person=responsible_person,
        registration_date=registration_date,
    )
    if form_error:
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data=assets_service.build_asset_form_data(
                name=name,
                category_id=category_id,
                initial_value=initial_value,
                responsible_person=responsible_person,
                registration_date=registration_date,
            ),
            filters=filters,
            message=form_error,
            message_kind="error",
        )

    try:
        assets_repo.create_asset(
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
            form_data=assets_service.build_asset_form_data(
                name=name,
                category_id=category_id,
                initial_value=initial_value,
                responsible_person=responsible_person,
                registration_date=registration_date,
            ),
            filters=filters,
            message="Selected category does not exist.",
            message_kind="error",
        )
    updated_total_assets = assets_repo.count_assets(filters)
    _, _, updated_total_pages = assets_service.normalize_paging(current_page, safe_page_size, updated_total_assets)
    target_page = updated_total_pages
    return render_fixed_assets_page(
        user["email"],
        assets_repo.list_assets(target_page, safe_page_size, filters),
        page=target_page,
        page_size=safe_page_size,
        total_assets=updated_total_assets,
        filters=filters,
        message="Fixed asset created successfully.",
        message_kind="success",
    )
