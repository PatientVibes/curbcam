"""Event feed (SSE) + history/CSV (history + CSV added in Slice D)."""

from __future__ import annotations

import csv
import datetime as dt
import io
from collections.abc import Iterator
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from curbcam.storage.repositories import EventFilter
from curbcam.web.deps import get_supervisor, require_session
from curbcam.web.streams import sse_generator
from curbcam.web.supervisor import Supervisor
from curbcam.web.templating import templates
from curbcam.web.units import display_to_kph, kph_to_display

router = APIRouter()

_PAGE = 24


@router.get("/api/events/stream")
def events_stream(
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    return StreamingResponse(sse_generator(sup), media_type="text/event-stream")


def _parse_filter(
    sup: Supervisor,
    start: str | None,
    end: str | None,
    min_speed: float | None,
    max_speed: float | None,
    direction: str | None,
) -> tuple[EventFilter, str]:
    units = sup.config_store.load().server.units
    f = EventFilter(direction=direction or None)
    if start:
        f.start = dt.datetime.combine(dt.date.fromisoformat(start), dt.time.min)
    if end:
        f.end = dt.datetime.combine(dt.date.fromisoformat(end), dt.time.max)
    if min_speed is not None:
        f.min_speed_kph = display_to_kph(min_speed, units)
    if max_speed is not None:
        f.max_speed_kph = display_to_kph(max_speed, units)
    return f, units


def _parse_cursor(cursor: str | None) -> tuple[dt.datetime, int] | None:
    if not cursor:
        return None
    ts_str, id_str = cursor.split("|", 1)
    return dt.datetime.fromisoformat(ts_str), int(id_str)


@router.get("/api/events", response_class=HTMLResponse)
def api_events(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    min_speed: float | None = None,
    max_speed: float | None = None,
    direction: str | None = None,
    cursor: str | None = None,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> HTMLResponse:
    f, units = _parse_filter(sup, start, end, min_speed, max_speed, direction)
    rows = sup.events.query(f, cursor=_parse_cursor(cursor), limit=_PAGE)
    next_cursor = f"{rows[-1].ts_utc.isoformat()}|{rows[-1].id}" if len(rows) == _PAGE else ""
    query = urlencode(
        {
            k: v
            for k, v in {
                "start": start,
                "end": end,
                "min_speed": min_speed,
                "max_speed": max_speed,
                "direction": direction,
            }.items()
            if v is not None
        }
    )
    return templates.TemplateResponse(
        request,
        "partials/events_rows.html",
        {"events": rows, "units": units, "next_cursor": next_cursor, "query": query},
    )


@router.get("/api/events.csv")
def api_events_csv(
    start: str | None = None,
    end: str | None = None,
    min_speed: float | None = None,
    max_speed: float | None = None,
    direction: str | None = None,
    _: None = Depends(require_session),
    sup: Supervisor = Depends(get_supervisor),
) -> StreamingResponse:
    f, units = _parse_filter(sup, start, end, min_speed, max_speed, direction)

    def rows() -> Iterator[str]:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "id",
                "ts_utc",
                "speed",
                "units",
                "direction",
                "frame_count",
                "track_len_px",
                "image_path",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        cursor: tuple[dt.datetime, int] | None = None
        while True:
            page = sup.events.query(f, cursor=cursor, limit=500)
            if not page:
                break
            for e in page:
                w.writerow(
                    [
                        e.id,
                        f"{e.ts_utc.isoformat()}Z",
                        round(kph_to_display(float(e.speed_kph), units), 1),
                        units,
                        e.direction,
                        e.frame_count,
                        e.track_len_px,
                        e.image_path,
                    ]
                )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
            cursor = (page[-1].ts_utc, page[-1].id)

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=curbcam-events.csv"},
    )
