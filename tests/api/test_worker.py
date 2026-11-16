"""Background worker: channel reports, unavailable speech provider, crash recovery."""
from __future__ import annotations

from sqlalchemy import text

from raahat.config import get_settings
from raahat.workers.main import Worker


def _worker(db) -> Worker:
    return Worker(get_settings(), db)


def test_worker_analyses_channel_reports(app, admin, operation, db):
    accepted = app.post("/api/v1/reports/channels/sms", headers=admin, json={
        "disaster_id": operation, "sender": "+919811111111", "message": "5 people trapped, water rising",
        "message_id": "sms-1",
    })
    assert accepted.status_code == 202, accepted.text
    worker = _worker(db)
    assert worker.run_once() == 1
    report = app.get(f"/api/v1/reports/{accepted.json()['report_id']}", headers=admin).json()
    assert report["processing_status"] == "processed"
    assert report["incident_reference"] == "INC-000001"
    with db() as session:
        beat = session.execute(text("SELECT details FROM worker_heartbeats")).scalar_one()
    assert beat["processed_total"] == 1
    status = app.get("/api/v1/system/status", headers=admin).json()
    assert next(c for c in status["components"] if c["key"] == "worker")["status"] == "operational"


def test_audio_without_speech_provider_is_flagged_not_invented(app, admin, operation, db, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    from raahat.application.intake import service as intake
    from raahat.domain.reports.report import ReportSubmission
    from raahat.domain.shared.enums import SourceType

    stored = intake.save_audio(tmp_path, data=b"RIFF....WAVEfmt fake audio", filename="call.wav")
    with db() as session:
        report, _ = intake.store_channel_report(session, ReportSubmission(
            disaster_id=operation, source_type=SourceType.WEB, raw_payload={"audio": stored},
            idempotency_key="voice-fixture-1",
        ))
    _worker(db).run_once()
    detail = app.get(f"/api/v1/reports/{report.id}", headers=admin).json()
    assert detail["original_text"] is None
    assert "not configured" in detail["processing_error"]
    assert detail["has_audio"] is True
    runs = {(r["stage"], r["status"]) for r in detail["processing_runs"]}
    assert ("transcription", "not_configured") in runs
    get_settings.cache_clear()


def test_interrupted_reports_return_to_the_queue(app, admin, operation, db):
    app.post("/api/v1/reports/channels/sms", headers=admin, json={
        "disaster_id": operation, "sender": "+919822222222", "message": "Help", "message_id": "sms-2"})
    with db() as session:
        session.execute(text("UPDATE reports SET processing_status = 'claimed'"))
        session.commit()
    worker = _worker(db)
    assert worker.recover() == 1
    assert worker.run_once() == 1
