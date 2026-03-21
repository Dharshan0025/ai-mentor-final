import json
import logging
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from db import db
from scheduler import run_scan_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Alerts"])

@router.get("/student/{student_id}/alerts")
async def get_alerts(student_id: str):
    """
    Return all unread proactive alerts for a student.
    Alerts are created by the nightly scheduler (APScheduler).
    Frontend polls this on load to show the notification badge.
    """
    alerts = await db.get_unread_alerts(student_id)
    count = len(alerts)
    return {
        "student_id": student_id,
        "unread_count": count,
        "alerts": alerts,
        "has_critical": any(a["severity"] == "critical" for a in alerts),
    }


@router.post("/student/{student_id}/alerts/{alert_id}/read")
async def dismiss_alert(student_id: str, alert_id: str):
    """Mark an alert as read (dismissed by the student)."""
    ok = await db.mark_alert_read(alert_id, student_id)
    return {"success": ok, "alert_id": alert_id}


@router.post("/student/{student_id}/alerts/scan")
async def trigger_scan(student_id: str):
    """
    Manual trigger — runs the attendance + sentiment scan immediately.
    Use this for testing without waiting for the nightly cron.
    """
    import asyncio
    asyncio.create_task(run_scan_now())
    return {
        "status": "scan_triggered",
        "message": "Attendance cliff scan started in background. Check /alerts in ~5 seconds.",
    }


@router.get("/student/{student_id}/alerts/stream")
async def stream_alerts(student_id: str, request: Request):
    """
    SSE endpoint — streams new alerts to the frontend in real-time.
    Keeps connection open, polls DB every 10s for new unread alerts,
    sends only newly-appeared alerts as SSE events.
    """

    async def event_generator():
        known_ids: set[str] = set()
        # Seed with current alerts so we don't re-fire them
        try:
            initial = await db.get_unread_alerts(student_id)
            known_ids = {a["id"] for a in initial}
        except Exception:
            pass

        # Send initial count so frontend can sync badge immediately
        yield f"event: count\ndata: {json.dumps({'unread_count': len(known_ids)})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                alerts = await db.get_unread_alerts(student_id)
                current_ids = {a["id"] for a in alerts}
                new_alerts = [a for a in alerts if a["id"] not in known_ids]

                if new_alerts:
                    for alert in new_alerts:
                        yield f"event: alert\ndata: {json.dumps(alert)}\n\n"
                    known_ids = current_ids

                # Always send a heartbeat count so badge stays accurate
                yield f"event: count\ndata: {json.dumps({'unread_count': len(current_ids)})}\n\n"
            except Exception as e:
                logger.warning(f"SSE alert stream error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(10)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
