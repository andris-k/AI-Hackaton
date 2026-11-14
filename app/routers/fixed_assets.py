from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Cookie, File, Form, Query, UploadFile
from fastapi.responses import HTMLResponse

from app import config
from app.logging_config import audit, diff_fields
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
_AUDITED_ASSET_FIELDS = (
    "name", "category", "quantity", "initial_value", "responsible_person", "registration_date",
)
_UPLOADS_ROOT = config.uploads_dir()
_FIXED_ASSET_UPLOAD_DIR = _UPLOADS_ROOT / "fixed-assets"


def _save_fixed_asset_image(image: UploadFile) -> tuple[str | None, str | None]:
    raw_filename = (image.filename or "").strip()
    if not raw_filename:
        return None, None

    content = image.file.read()
    validation_error = assets_service.validate_image_upload(
        filename=raw_filename,
        content_type=image.content_type,
        size_bytes=len(content),
    )
    if validation_error:
        return None, validation_error

    extension = Path(raw_filename).suffix.lower()
    stored_name = f"{uuid4().hex}{extension}"
    _FIXED_ASSET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_path = _FIXED_ASSET_UPLOAD_DIR / stored_name
    target_path.write_bytes(content)
    return f"fixed-assets/{stored_name}", None


def _delete_uploaded_image(image_path: str | None) -> None:
    normalized_path = (image_path or "").strip()
    if not normalized_path:
        return

    target_path = (_UPLOADS_ROOT / normalized_path).resolve()
    uploads_root = _UPLOADS_ROOT.resolve()
    if not str(target_path).startswith(str(uploads_root)):
        return
    if target_path.exists() and target_path.is_file():
        target_path.unlink()


@router.get("/fixed-assets", response_class=HTMLResponse)
def fixed_assets_page(
    session_token: str | None = Cookie(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str = Query(default=""),
    category: list[str] = Query(default=[]),
    initial_value_from: str = Query(default=""),
    initial_value_to: str = Query(default=""),
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
        initial_value_from=initial_value_from,
        initial_value_to=initial_value_to,
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
    initial_value_from: str = Query(default=""),
    initial_value_to: str = Query(default=""),
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
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value_from=initial_value_from,
        initial_value_to=initial_value_to,
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
    initial_value_from: str = Query(default=""),
    initial_value_to: str = Query(default=""),
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
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    if not assets_repo.list_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    filters = assets_service.build_filters(
        name=name,
        category=category,
        initial_value_from=initial_value_from,
        initial_value_to=initial_value_to,
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
    quantity: int = Form(...),
    initial_value: float = Form(...),
    responsible_person: str = Form(...),
    registration_date: str = Form(...),
    image: UploadFile | None = File(default=None),
    page: int = Form(default=1),
    page_size: int = Form(default=20),
    name_filter: str = Form(default=""),
    category_filter: str = Form(default=""),
    initial_value_from_filter: str = Form(default=""),
    initial_value_to_filter: str = Form(default=""),
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
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    if not assets_repo.list_categories():
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "No Categories Available",
            "Create at least one category before editing fixed assets.",
            '<div class="links"><a href="/fixed-asset-categories">Manage categories</a><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="No categories found.",
            message_kind="error",
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    filters = assets_service.build_filters(
        name=name_filter,
        category=category_filter,
        initial_value_from=initial_value_from_filter,
        initial_value_to=initial_value_to_filter,
        responsible_person=responsible_person_filter,
        registration_date_from=registration_date_from_filter,
        registration_date_to=registration_date_to_filter,
    )
    safe_page = max(1, page)
    _, safe_page_size, _ = assets_service.normalize_paging(safe_page, page_size, 1)

    form_error = assets_service.validate_asset_form(
        name=name,
        category_id=category_id,
        quantity=quantity,
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

    previous_image_path = str(fixed_asset["image_path"] or "").strip() or None
    image_path_to_save = previous_image_path
    new_image_path: str | None = None
    if image and (image.filename or "").strip():
        uploaded_path, image_error = _save_fixed_asset_image(image)
        if image_error:
            return render_edit_fixed_asset_page(
                user["email"],
                fixed_asset,
                page=safe_page,
                page_size=safe_page_size,
                filters=filters,
                message=image_error,
                message_kind="error",
            )
        new_image_path = uploaded_path
        image_path_to_save = uploaded_path

    try:
        updated = assets_repo.update_asset(
            fixed_asset_id=fixed_asset_id,
            name=name.strip(),
            category_id=category_id.strip(),
            quantity=quantity,
            initial_value=initial_value,
            responsible_person=responsible_person.strip(),
            registration_date=registration_date,
            image_path=image_path_to_save,
        )
    except ValueError:
        if new_image_path:
            _delete_uploaded_image(new_image_path)
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
        if new_image_path:
            _delete_uploaded_image(new_image_path)
        return render_page(
            "AI Hackaton Edit Fixed Asset",
            "Fixed Asset Not Found",
            "The requested fixed asset does not exist.",
            '<div class="links"><a href="/fixed-assets">Back to fixed assets</a></div>',
            message="Fixed asset not found.",
            message_kind="error",
            current_email=user["email"],
            active_nav="fixed-assets",
        )

    if new_image_path and previous_image_path and new_image_path != previous_image_path:
        _delete_uploaded_image(previous_image_path)

    audit(
        "asset.updated",
        asset_id=fixed_asset_id,
        name=updated["name"],
        changes=diff_fields(fixed_asset, updated, _AUDITED_ASSET_FIELDS),
        image_replaced=bool(new_image_path),
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
    initial_value_from: str = Query(default=""),
    initial_value_to: str = Query(default=""),
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
        initial_value_from=initial_value_from,
        initial_value_to=initial_value_to,
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
            current_email=user["email"],
            active_nav="fixed-assets",
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
    quantity: int = Form(...),
    initial_value: float = Form(...),
    responsible_person: str = Form(...),
    registration_date: str = Form(...),
    image: UploadFile | None = File(default=None),
    page: int = Form(default=1),
    page_size: int = Form(default=20),
    name_filter: str = Form(default=""),
    category_filter: str = Form(default=""),
    initial_value_from_filter: str = Form(default=""),
    initial_value_to_filter: str = Form(default=""),
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
        initial_value_from=initial_value_from_filter,
        initial_value_to=initial_value_to_filter,
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
        quantity=quantity,
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
                quantity=quantity,
                initial_value=initial_value,
                responsible_person=responsible_person,
                registration_date=registration_date,
            ),
            filters=filters,
            message=form_error,
            message_kind="error",
        )

    uploaded_image_path: str | None = None
    if image and (image.filename or "").strip():
        uploaded_image_path, image_error = _save_fixed_asset_image(image)
        if image_error:
            return render_add_fixed_asset_page(
                user["email"],
                page=current_page,
                page_size=safe_page_size,
                categories=categories,
                form_data=assets_service.build_asset_form_data(
                    name=name,
                    category_id=category_id,
                    quantity=quantity,
                    initial_value=initial_value,
                    responsible_person=responsible_person,
                    registration_date=registration_date,
                ),
                filters=filters,
                message=image_error,
                message_kind="error",
            )

    try:
        created = assets_repo.create_asset(
            name=name.strip(),
            category_id=category_id.strip(),
            quantity=quantity,
            initial_value=initial_value,
            responsible_person=responsible_person.strip(),
            registration_date=registration_date,
            image_path=uploaded_image_path,
        )
    except ValueError:
        if uploaded_image_path:
            _delete_uploaded_image(uploaded_image_path)
        return render_add_fixed_asset_page(
            user["email"],
            page=current_page,
            page_size=safe_page_size,
            categories=categories,
            form_data=assets_service.build_asset_form_data(
                name=name,
                category_id=category_id,
                quantity=quantity,
                initial_value=initial_value,
                responsible_person=responsible_person,
                registration_date=registration_date,
            ),
            filters=filters,
            message="Selected category does not exist.",
            message_kind="error",
        )
    audit(
        "asset.created",
        asset_id=created["id"],
        name=created["name"],
        category=created["category"],
        quantity=created["quantity"],
        initial_value=created["initial_value"],
        responsible_person=created["responsible_person"],
        has_image=bool(uploaded_image_path),
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


@router.post("/fixed-assets/id/{fixed_asset_id}/delete", response_class=HTMLResponse)
def delete_fixed_asset_route(
    fixed_asset_id: str,
    session_token: str | None = Cookie(default=None),
    page: int = Form(default=1),
    page_size: int = Form(default=20),
    name_filter: str = Form(default=""),
    category_filter: str = Form(default=""),
    initial_value_from_filter: str = Form(default=""),
    initial_value_to_filter: str = Form(default=""),
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
        initial_value_from=initial_value_from_filter,
        initial_value_to=initial_value_to_filter,
        responsible_person=responsible_person_filter,
        registration_date_from=registration_date_from_filter,
        registration_date_to=registration_date_to_filter,
    )

    asset_before_delete = assets_repo.get_asset_by_id(fixed_asset_id)
    deleted = assets_repo.delete_asset(fixed_asset_id)
    if deleted and asset_before_delete is not None:
        _delete_uploaded_image(str(asset_before_delete["image_path"] or "").strip() or None)
        audit(
            "asset.deleted",
            asset_id=fixed_asset_id,
            name=asset_before_delete["name"],
            category=asset_before_delete["category"],
            quantity=asset_before_delete["quantity"],
            initial_value=asset_before_delete["initial_value"],
        )
    total_assets = assets_repo.count_assets(filters)
    current_page, safe_page_size, _ = assets_service.normalize_paging(page, page_size, total_assets)
    assets = assets_repo.list_assets(current_page, safe_page_size, filters)

    if not deleted:
        return render_fixed_assets_page(
            user["email"],
            assets,
            page=current_page,
            page_size=safe_page_size,
            total_assets=total_assets,
            filters=filters,
            message="Fixed asset not found or already deleted.",
            message_kind="error",
        )

    return render_fixed_assets_page(
        user["email"],
        assets,
        page=current_page,
        page_size=safe_page_size,
        total_assets=total_assets,
        filters=filters,
        message="Fixed asset deleted successfully.",
        message_kind="success",
    )
