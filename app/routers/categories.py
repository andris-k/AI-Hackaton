from __future__ import annotations

from fastapi import APIRouter, Cookie, Form
from fastapi.responses import HTMLResponse

from app.logging_config import audit
from app.repositories import fixed_assets_repository as assets_repo
from app.services import auth_service
from app.services import fixed_assets_service as assets_service
from app.views.pages import (
    render_edit_fixed_asset_category_page,
    render_fixed_asset_categories_page,
    render_login_page,
    render_page,
)

router = APIRouter()


@router.get("/fixed-asset-categories", response_class=HTMLResponse)
def fixed_asset_categories_page(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    categories = assets_repo.list_categories_with_usage()
    return render_fixed_asset_categories_page(user["email"], categories)


@router.post("/fixed-asset-categories", response_class=HTMLResponse)
def create_fixed_asset_category_route(
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    normalized_name, category_error = assets_service.validate_category_name(name)
    if category_error:
        return render_fixed_asset_categories_page(
            user["email"],
            assets_repo.list_categories_with_usage(),
            message=category_error,
            message_kind="error",
        )

    try:
        created = assets_repo.create_category(normalized_name)
    except Exception:
        return render_fixed_asset_categories_page(
            user["email"],
            assets_repo.list_categories_with_usage(),
            message="Unable to create category. It may already exist.",
            message_kind="error",
        )

    audit("category.created", category_id=created["id"], name=created["name"])
    return render_fixed_asset_categories_page(
        user["email"],
        assets_repo.list_categories_with_usage(),
        message="Category created successfully.",
        message_kind="success",
    )


@router.get("/fixed-asset-categories/{category_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_category_page(
    category_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    category = assets_repo.get_category_by_id(category_id)
    if category is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset Category",
            "Category Not Found",
            "The requested category does not exist.",
            '<div class="links"><a href="/fixed-asset-categories">Back to categories</a></div>',
            message="Category not found.",
            message_kind="error",
            current_email=user["email"],
            active_nav="categories",
        )

    return render_edit_fixed_asset_category_page(user["email"], category)


@router.post("/fixed-asset-categories/{category_id}/edit", response_class=HTMLResponse)
def edit_fixed_asset_category_route(
    category_id: str,
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    category = assets_repo.get_category_by_id(category_id)
    if category is None:
        return render_page(
            "AI Hackaton Edit Fixed Asset Category",
            "Category Not Found",
            "The requested category does not exist.",
            '<div class="links"><a href="/fixed-asset-categories">Back to categories</a></div>',
            message="Category not found.",
            message_kind="error",
            current_email=user["email"],
            active_nav="categories",
        )

    normalized_name, category_error = assets_service.validate_category_name(name)
    if category_error:
        return render_edit_fixed_asset_category_page(
            user["email"],
            category,
            message=category_error,
            message_kind="error",
        )

    try:
        updated = assets_repo.update_category(category_id, normalized_name)
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
            current_email=user["email"],
            active_nav="categories",
        )

    if category["name"] != updated["name"]:
        audit("category.renamed", category_id=category_id, changes={"name": [category["name"], updated["name"]]})
    return render_edit_fixed_asset_category_page(
        user["email"],
        updated,
        message="Category updated successfully.",
        message_kind="success",
    )


@router.post("/fixed-asset-categories/{category_id}/delete", response_class=HTMLResponse)
def delete_fixed_asset_category_route(
    category_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to manage fixed asset categories.")

    category_before_delete = assets_repo.get_category_by_id(category_id)
    if category_before_delete is None:
        return render_fixed_asset_categories_page(
            user["email"],
            assets_repo.list_categories_with_usage(),
            message="Category not found or already deleted.",
            message_kind="error",
        )
    deleted = assets_repo.delete_category(category_id)
    if not deleted:
        return render_fixed_asset_categories_page(
            user["email"],
            assets_repo.list_categories_with_usage(),
            message="Cannot delete category while it is used by fixed assets.",
            message_kind="error",
        )

    audit(
        "category.deleted",
        category_id=category_id,
        name=category_before_delete["name"] if category_before_delete is not None else None,
    )
    return render_fixed_asset_categories_page(
        user["email"],
        assets_repo.list_categories_with_usage(),
        message="Category deleted successfully.",
        message_kind="success",
    )
