#!/usr/bin/env python3
"""Raahat Demo Runner — interactive 8-milestone demo using Kerala 2018 archival flood audio.

Usage:
    # Docker Compose stack (default)
    python scripts/demo_run.py --scenario demo/scenario.json

    # Local dev server
    python scripts/demo_run.py --base-url http://localhost:8000 --scenario demo/scenario.json

    # Dry-run (shows plan, no API calls)
    python scripts/demo_run.py --dry-run

    # Custom pacing
    python scripts/demo_run.py --pause 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Milestone definitions
# ---------------------------------------------------------------------------

_MILESTONES = [
    {
        "id": 1,
        "title": "Platform Health Check",
        "description": "Verify all Raahat services are operational",
        "audio_index": None,  # no audio for health check
    },
    {
        "id": 2,
        "title": "Flood Distress Call — Alappuzha Boat Jetty",
        "description": "Caller reports rapidly rising water near Alappuzha, 3 people stranded",
        "audio_index": 0,
        "coords": (9.4981, 76.3388),
    },
    {
        "id": 3,
        "title": "Medical Emergency — Ernakulam Hospital Area",
        "description": "Caller reports a bedridden patient unable to evacuate",
        "audio_index": 1,
        "coords": (9.9816, 76.2999),
    },
    {
        "id": 4,
        "title": "Trapped Residents — Chalakudy River Bridge",
        "description": "Multiple families trapped, water entering ground floor",
        "audio_index": 2,
        "coords": (10.3024, 76.3337),
    },
    {
        "id": 5,
        "title": "Rescue Request — Pamba River Ghat",
        "description": "Pilgrim stranded at river ghat, water still rising",
        "audio_index": 3,
        "coords": (9.3860, 76.5540),
    },
    {
        "id": 6,
        "title": "Shelter Overflow — Munnar Town Centre",
        "description": "Relief camp coordinator reports capacity issues",
        "audio_index": 4,
        "coords": (10.0889, 77.0595),
    },
    {
        "id": 7,
        "title": "Marine Drive — Kochi Rescue Coordination",
        "description": "Coordinator requests NDRF boat diversion to north sector",
        "audio_index": 5,
        "coords": (9.9657, 76.2824),
    },
    {
        "id": 8,
        "title": "Live Dashboard — Summary & Dispatch Proposals",
        "description": "Show Operator Console — all incidents triaged, dispatch proposals pending human approval",
        "audio_index": None,
    },
]

_PRIORITY_LABEL = {
    "critical_review": "🔴 CRITICAL",
    "urgent": "🟠 URGENT",
    "standard": "🟡 STANDARD",
    "low": "🟢 LOW",
    "unassessed": "⚪ UNASSESSED",
}


def _banner(text: str) -> None:
    width = 72
    print("\n" + "═" * width)
    print(f"  {text}")
    print("═" * width)


def _step(label: str, value: str = "") -> None:
    print(f"  {'▸'} {label}: {value}" if value else f"  {'▸'} {label}")


def _ok(msg: str) -> None:
    print(f"  ✔  {msg}")


def _warn(msg: str) -> None:
    print(f"  ⚠  {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _health_check(client: httpx.Client) -> bool:
    try:
        r = client.get("/healthz", timeout=5)
        return r.status_code == 200
    except httpx.RequestError:
        return False


def _run_demo_scenario(
    client: httpx.Client,
    disaster_id: str,
    audio_index: int,
    lat: float,
    lon: float,
    language_hint: str = "ml",
) -> dict[str, Any]:
    payload = {
        "disaster_id": disaster_id,
        "audio_index": audio_index,
        "latitude": lat,
        "longitude": lon,
        "language_hint": language_hint,
    }
    r = client.post("/api/v1/demo/run-scenario", json=payload, timeout=60)
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


# ---------------------------------------------------------------------------
# Milestone runners
# ---------------------------------------------------------------------------

def _run_milestone_1(client: httpx.Client, base_url: str, dry_run: bool) -> None:
    _banner("MILESTONE 1 — Platform Health Check")
    _step("Endpoint", f"{base_url}/healthz")
    if dry_run:
        _ok("[DRY RUN] Would verify: HTTP 200 from /healthz")
        return
    ok = _health_check(client)
    if ok:
        _ok("All services operational")
    else:
        _warn("Health check failed — verify Docker Compose stack is running")
        sys.exit(1)


def _run_audio_milestone(
    client: httpx.Client,
    base_url: str,
    disaster_id: str,
    milestone: dict,
    dry_run: bool,
    pause: float,
) -> None:
    mid = milestone["id"]
    title = milestone["title"]
    desc = milestone["description"]
    audio_index = milestone["audio_index"]
    lat, lon = milestone.get("coords", (9.4981, 76.3388))

    _banner(f"MILESTONE {mid} — {title}")
    _step("Description", desc)
    _step("Audio source", f"Kerala 2018 archival recording #{audio_index + 1}")
    _step("Coordinates", f"{lat:.4f}°N, {lon:.4f}°E")
    _step("Endpoint", f"{base_url}/api/v1/demo/run-scenario")

    if dry_run:
        _ok(f"[DRY RUN] Would POST audio_index={audio_index} to /api/v1/demo/run-scenario")
        return

    print()
    print("  Processing audio through pipeline …")
    t0 = time.monotonic()
    try:
        result = _run_demo_scenario(client, disaster_id, audio_index, lat, lon)
    except httpx.HTTPStatusError as exc:
        _warn(f"API error {exc.response.status_code}: {exc.response.text[:200]}")
        return
    elapsed = time.monotonic() - t0

    priority_raw = result.get("priority", "unassessed")
    priority_label = _PRIORITY_LABEL.get(priority_raw, priority_raw)

    print()
    _ok(f"Pipeline completed in {elapsed:.2f}s (server: {result.get('execution_time_ms', 0):.0f}ms)")
    _step("Transcript", result.get("transcript", "")[:120] or "(silent/non-speech audio)")
    _step("Speech detected", "Yes" if result.get("has_speech") else "No")
    _step("Triage priority", priority_label)
    reasons = result.get("priority_reasons", [])
    for r in reasons[:3]:
        print(f"       • {r}")
    _step("Location resolved", result.get("location_label") or "(GPS coordinates used)")
    if result.get("proposed_resource_name"):
        _step("Proposed unit", f"{result['proposed_resource_name']} (status: PROPOSED — awaiting human approval)")
    _step("Incident ID", result.get("incident_id", "?"))
    _step("Ticket URL", f"{base_url}/api/v1/reports/{result.get('report_id')}/ticket")
    if pause > 0:
        time.sleep(pause)


def _run_milestone_8(base_url: str, dry_run: bool) -> None:
    _banner("MILESTONE 8 — Live Dashboard Summary")
    print()
    _step("Operator Console", f"{base_url}/console/")
    _step("API Docs", f"{base_url}/docs")
    _step("Metrics", f"{base_url}/metrics")
    print()
    print("  All dispatch proposals are in PROPOSED state.")
    print("  No autonomous action has been taken.")
    print("  Human dispatcher must approve each assignment.")
    print()
    _ok("Demo complete — Raahat deterministic safety-first platform demonstrated.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Raahat demo runner — Kerala 2018 flood scenario",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("RAAHAT_BASE_URL", "http://localhost:8080"),
        help="Base URL of the Raahat API (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--scenario",
        default="demo/scenario.json",
        help="Path to scenario.json produced by seed_demo_data.py",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the demo plan without making API calls",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=2.0,
        help="Seconds to pause between milestones (default: 2)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    scenario_path = Path(args.scenario)

    if not scenario_path.exists():
        print(
            f"ERROR: scenario file not found: {scenario_path}\n"
            "Run:  python scripts/seed_demo_data.py --db-url <your-db-url>",
            file=sys.stderr,
        )
        sys.exit(1)

    scenario = json.loads(scenario_path.read_text())
    disaster_id = scenario["disaster_id"]
    disaster_name = scenario.get("disaster_name", "Demo Disaster")

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║           RAAHAT — Disaster Intelligence Platform Demo              ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Scenario  : {disaster_name}")
    print(f"  Disaster  : {disaster_id}")
    print(f"  API URL   : {base_url}")
    print("  Audio src : Kerala Flood 2018 archival recordings (Christ College DSpace)")
    print(f"  Dry-run   : {args.dry_run}")
    print()

    client = httpx.Client(base_url=base_url)

    # Milestone 1 — health check
    _run_milestone_1(client, base_url, args.dry_run)
    if args.pause > 0 and not args.dry_run:
        time.sleep(args.pause)

    # Milestones 2–7 — audio triage
    for milestone in _MILESTONES[1:-1]:
        _run_audio_milestone(
            client, base_url, disaster_id, milestone, args.dry_run, args.pause
        )

    # Milestone 8 — summary
    _run_milestone_8(base_url, args.dry_run)


if __name__ == "__main__":
    main()

