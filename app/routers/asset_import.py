"""Importing fixed assets from a CSV file: upload, preview, confirm."""

from __future__ import annotations

import re
import secrets
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Cookie, File, Form, UploadFile
from fastapi.responses import HTMLResponse, Response

from app.logging_config import audit, audit_many
from app.repositories import fixed_assets_repository as assets_repo
from app.repositories import locations_repository as locations_repo
from app.services import asset_import_service as import_svc
from app.services import auth_service
from app.views.pages import render_fixed_asset_import_page, render_login_page

router = APIRouter()
_LOGIN_MESSAGE = "Please log in to import fixed assets."
# Uploads wait here between preview and confirm. Not under the uploads folder,
# which is served publicly.
_PENDING_DIR = Path(tempfile.gettempdir()) / "asset-registry-imports"
_PENDING_MAX_AGE_SECONDS = 60 * 60
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _pending_path(user_id: int, token: str) -> Path | None:
    if not _TOKEN_RE.match(token):
        return None
    return _PENDING_DIR / f"{int(user_id)}-{token}.csv"


def _remove_old_pending_files() -> None:
    if not _PENDING_DIR.exists():
        return
    cutoff = time.time() - _PENDING_MAX_AGE_SECONDS
    for path in _PENDING_DIR.glob("*.csv"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def _preview(data: bytes) -> import_svc.ImportPreview:
    return import_svc.parse_assets_csv(
        data,
        existing_categories=[row["name"] for row in assets_repo.list_categories()],
        existing_locations=[row["name"] for row in locations_repo.list_all()],
        existing_asset_names=assets_repo.list_asset_names(),
    )


@router.get("/fixed-assets/import", response_class=HTMLResponse)
def import_page(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    return render_fixed_asset_import_page(user["email"])


@router.get("/fixed-assets/import/template.csv")
def import_template(session_token: str | None = Cookie(default=None)) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    return Response(
        content=import_svc.template_csv().encode("utf-8-sig"),  # the BOM makes Excel read UTF-8
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fixed-assets-import-template.csv"'},
    )


@router.post("/fixed-assets/import", response_class=HTMLResponse)
async def upload_import_file(
    session_token: str | None = Cookie(default=None),
    file: UploadFile | None = File(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    if file is None or not (file.filename or "").strip():
        return render_fixed_asset_import_page(user["email"], message="Choose a CSV file to upload.", message_kind="error")

    data = await file.read(import_svc.MAX_FILE_BYTES + 1)
    try:
        preview = _preview(data)
    except import_svc.ImportFileError as error:
        return render_fixed_asset_import_page(user["email"], message=str(error), message_kind="error")

    token = ""
    if preview.can_import:
        _remove_old_pending_files()
        _PENDING_DIR.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        _pending_path(int(user["id"]), token).write_bytes(data)
    return render_fixed_asset_import_page(
        user["email"], preview=preview, token=token, filename=file.filename or ""
    )


@router.post("/fixed-assets/import/confirm", response_class=HTMLResponse)
def confirm_import(
    session_token: str | None = Cookie(default=None),
    token: str = Form(default=""),
    filename: str = Form(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    path = _pending_path(int(user["id"]), token)
    if path is None or not path.exists():
        return render_fixed_asset_import_page(
            user["email"],
            message="This upload has expired or was already imported. Upload the file again.",
            message_kind="error",
        )

    data = path.read_bytes()
    try:
        preview = _preview(data)  # check again: categories or locations may have changed since
    except import_svc.ImportFileError as error:
        path.unlink(missing_ok=True)
        return render_fixed_asset_import_page(user["email"], message=str(error), message_kind="error")
    if not preview.can_import:
        path.unlink(missing_ok=True)
        return render_fixed_asset_import_page(
            user["email"],
            preview=preview,
            filename=filename,
            message="Some rows are no longer valid. Fix them and upload the file again.",
            message_kind="error",
        )

    result = assets_repo.import_assets(
        [
            {
                "name": row.name,
                "category": row.category,
                "location": row.location,
                "quantity": row.quantity,
                "initial_value": row.initial_value,
                "responsible_person": row.responsible_person,
                "registration_date": row.registration_date,
            }
            for row in preview.rows
        ]
    )
    path.unlink(missing_ok=True)

    audit(
        "asset.imported",
        file=filename or None,
        asset_count=len(result["asset_ids"]),
        created_categories=", ".join(result["created_categories"]) or None,
        created_locations=", ".join(result["created_locations"]) or None,
    )
    # One "created" event per asset, so each asset's History shows where it came from.
    audit_many(
        "asset.created",
        [
            {
                "asset_id": asset_id,
                "name": row.name,
                "category": row.category,
                "location": row.location or None,
                "quantity": row.quantity,
                "initial_value": row.initial_value,
                "responsible_person": row.responsible_person,
                "source": "CSV import",
            }
            for asset_id, row in zip(result["asset_ids"], preview.rows)
        ],
    )

    return render_fixed_asset_import_page(
        user["email"],
        imported=result,
        filename=filename,
        message=f"Imported {len(result['asset_ids'])} fixed assets.",
        message_kind="success",
    )
