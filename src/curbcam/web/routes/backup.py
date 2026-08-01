"""Export and import settings as YAML, so a working setup survives an SD card.

Recovering a curbcam previously meant re-running the wizard and re-measuring the
calibration by hand. Export downloads the current curbcam.yaml; import validates
an uploaded one, saves it, and restarts the pipeline.

Deliberately excluded from the export:

  Calibration   lives in SQLite, is camera-position specific, and would be
                actively harmful to restore onto a differently-aimed camera --
                it would produce confident, wrong speeds.
  Secrets       the admin password hash and stream tokens live in auth.json.
                Exporting them would turn a config backup into a credential
                file, and it is the sort of thing people paste into issues.

MQTT credentials ARE included, because they are part of the alert config the
user typed in and would otherwise have to retype. The download is therefore
sensitive; the UI says so.
"""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from markupsafe import escape
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from curbcam.config.schema import Settings
from curbcam.localtime import now_utc
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.supervisor import Supervisor

router = APIRouter()

# Refuse anything larger before parsing. A settings file is well under 4 KB; the
# limit exists so an uploaded multi-megabyte file cannot be read into memory and
# handed to the YAML parser.
_MAX_UPLOAD_BYTES = 256 * 1024


@router.get("/api/settings/export")
def export_settings(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> Response:
    raw = sup.config_store.load_raw()
    body = yaml.safe_dump(raw, sort_keys=True, default_flow_style=False)
    stamp = now_utc().strftime("%Y%m%d-%H%M%S")
    header = (
        "# curbcam settings export\n"
        f"# generated {now_utc().isoformat(timespec='seconds')}\n"
        "#\n"
        "# Does NOT include calibration (camera-position specific, stored in the\n"
        "# database) or credentials (admin password, stream tokens).\n"
        "# May contain an MQTT username/password if you configured one.\n"
    )
    return Response(
        content=header + body,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="curbcam-settings-{stamp}.yaml"'},
    )


def _result(ok: bool, message: str) -> HTMLResponse:
    css = "test-ok" if ok else "test-fail"
    prefix = "Imported" if ok else "Not imported"
    # 200 regardless: htmx swaps this fragment into the page, and it ignores
    # error-status bodies by default, so a 4xx would show the user nothing.
    return HTMLResponse(
        f'<span class="alert-test-result {css}">{prefix} — {escape(message)}</span>',
        status_code=200,
    )


@router.post("/api/settings/import", response_class=HTMLResponse)
async def import_settings(
    request: Request,
    file: UploadFile = File(...),
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    payload = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(payload) > _MAX_UPLOAD_BYTES:
        return _result(False, "File is too large to be a settings export.")
    if not payload.strip():
        return _result(False, "File is empty.")

    try:
        # safe_load, never load: an imported file is untrusted input, and full
        # YAML load can construct arbitrary Python objects.
        parsed: Any = yaml.safe_load(payload.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return _result(False, f"Not valid YAML: {str(exc)[:200]}")

    if not isinstance(parsed, dict):
        return _result(False, "Expected a mapping of settings sections at the top level.")

    try:
        Settings.model_validate(parsed)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        return _result(False, f"{where}: {first['msg']}")

    # Persist the uploaded mapping rather than a dump of the validated model, so
    # keys the current version does not know about are preserved rather than
    # silently dropped on a downgrade/upgrade round trip.
    sup.config_store.save_raw(parsed)
    await run_in_threadpool(sup.restart)
    count = sum(len(v) for v in parsed.values() if isinstance(v, dict))
    return _result(True, f"{count} settings restored. Detector restarting.")
