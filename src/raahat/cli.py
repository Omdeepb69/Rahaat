"""Host-side administration commands.

    python -m raahat.cli provision-accounts --all > credentials.csv
    python -m raahat.cli provision-accounts --states 32,30 --reset
    python -m raahat.cli create-admin --username NAME --full-name "Full Name"
    python -m raahat.cli reset-password --username NAME
    python -m raahat.cli import-landmarks --bbox SOUTH,WEST,NORTH,EAST
    python -m raahat.cli check-config

These run on the machine that hosts the database. They are how the first
account is created: the application ships with no default credentials.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from raahat.application.identity import service as identity
from raahat.config import ConfigurationError, get_settings
from raahat.infrastructure.database.models.location import LandmarkModel
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.providers.base import ProviderError
from raahat.infrastructure.providers.geo import OverpassClient
from raahat.security.passwords import WeakPasswordError
from raahat.security.permissions import Role


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    return first


def _sessions():
    return get_sync_sessionmaker(create_sync_engine(get_settings().database_url))


def create_admin(args: argparse.Namespace) -> int:
    password = _read_password(args.password_stdin)
    with _sessions()() as session:
        try:
            user = identity.create_user(
                session, username=args.username, full_name=args.full_name, role=Role.ADMIN,
                password=password, created_by=None, must_change_password=False,
            )
        except (identity.IdentityError, WeakPasswordError) as exc:
            print(f"Not created: {exc}", file=sys.stderr)
            return 1
        session.commit()
        print(f"Administrator '{user.username}' created.")
    return 0


def reset_password(args: argparse.Namespace) -> int:
    password = _read_password(args.password_stdin)
    with _sessions()() as session:
        user = identity.get_user_by_username(session, args.username)
        if user is None:
            print("No such user", file=sys.stderr)
            return 1
        try:
            identity.set_password(
                session, user=user, new_password=password, actor_id=user.id,
                require_change_on_next_login=False,
            )
        except WeakPasswordError as exc:
            print(f"Not changed: {exc}", file=sys.stderr)
            return 1
        user.is_active = True
        session.commit()
        print(f"Password for '{user.username}' changed; existing sessions were ended.")
    return 0


def import_landmarks(args: argparse.Namespace) -> int:
    """Import named landmark features from OpenStreetMap for a bounding box."""
    try:
        south, west, north, east = (float(v) for v in args.bbox.split(","))
    except ValueError:
        print("--bbox must be SOUTH,WEST,NORTH,EAST in decimal degrees", file=sys.stderr)
        return 1
    settings = get_settings()
    client = OverpassClient(base_url=args.overpass_url, user_agent=settings.http_user_agent)
    try:
        landmarks = client.fetch_landmarks((south, west, north, east))
    except ProviderError as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    imported_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for landmark in landmarks:
        # One searchable row per distinct name so local-script names match too.
        names = [landmark.name, *landmark.alt_names]
        for index, name in enumerate(dict.fromkeys(names)):
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "external_id": landmark.osm_ref if index == 0 else f"{landmark.osm_ref}#{index}",
                    "source": "osm",
                    "name": name[:255],
                    "kind": landmark.kind,
                    "salience": 1.0,
                    "location": f"SRID=4326;POINT({landmark.longitude} {landmark.latitude})",
                    "metadata_": {
                        "tags": landmark.tags,
                        "primary_name": landmark.name,
                        "licence": "OpenStreetMap contributors, ODbL 1.0",
                        "imported_at": imported_at,
                    },
                }
            )
    if not rows:
        print("No named landmarks found in that area.")
        return 0
    with _sessions()() as session:
        for start in range(0, len(rows), 500):
            statement = insert(LandmarkModel).values(rows[start : start + 500])
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["source", "external_id"],
                    index_where=text("external_id IS NOT NULL"),
                    set_={
                        "name": statement.excluded.name,
                        "kind": statement.excluded.kind,
                        "location": statement.excluded.location,
                        "metadata": statement.excluded["metadata"],
                    },
                )
            )
        session.commit()
        total = session.execute(text("SELECT count(*) FROM landmarks WHERE source = 'osm'")).scalar_one()
    print(
        f"Imported {len(landmarks)} features as {len(rows)} searchable names. "
        f"{total} OpenStreetMap landmark names are now stored."
    )
    return 0


def check_config(_: argparse.Namespace) -> int:
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    def state(value: object) -> str:
        return "set" if value else "not set"

    print(f"environment            {settings.environment}")
    print(f"secret key             {'TEMPORARY (set RAAHAT_SECRET_KEY)' if settings.secret_key_is_ephemeral else 'set'}")
    print(f"cors origins           {', '.join(settings.cors_allowed_origins) or 'none'}")
    print(f"public intake          {'enabled' if settings.public_intake_enabled else 'disabled'}")
    print(f"speech (Gnani) key     {state(settings.gnani_api_key)}")
    print(f"text model provider    {settings.llm_provider}")
    print(f"  evon api base        {state(settings.evon_api_base)}")
    print(f"  gemini api key       {state(settings.gemini_api_key)}")
    print(f"geocoder               {settings.geocoder_provider}")
    print(f"routing                {settings.routing_provider} ({state(settings.osrm_base_url)})")
    print(f"alert feed             {state(settings.cap_alert_feed_url)}")
    return 0


def provision_accounts(args: argparse.Namespace) -> int:
    """Create control room accounts and print their generated passwords as CSV.

    Passwords are printed once and stored only as hashes. Existing accounts
    keep their password unless --reset is given.
    """
    import csv

    from raahat.security.jurisdiction import Jurisdiction, directory

    ref = directory()
    wanted = {c.strip() for c in (args.states or "").split(",") if c.strip()}
    unknown = wanted - set(ref.by_state)
    if unknown:
        print(f"Unknown state codes: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 1
    targets: list[Jurisdiction] = []
    if args.national or args.all:
        targets.append(Jurisdiction())
    for state in ref.states:
        if not (args.all or state.code in wanted):
            continue
        targets.append(Jurisdiction(state.code))
        if not args.no_districts:
            targets.extend(Jurisdiction(state.code, d.code) for d in state.districts)
    if not targets:
        print("Nothing selected: pass --all, --national or --states", file=sys.stderr)
        return 1

    writer = csv.writer(sys.stdout)
    writer.writerow(["level", "state", "district", "account", "password"])
    created = kept = 0
    with _sessions()() as session:
        for target in targets:
            issued = identity.provision_jurisdiction_account(
                session, jurisdiction=target, created_by=None, reset_existing=args.reset
            )
            if issued.password is None:
                kept += 1
                continue
            created += 1
            writer.writerow([
                target.level, target.state_name or "", target.district_name or "",
                issued.username, issued.password,
            ])
        session.commit()
    print(f"{created} passwords issued, {kept} existing accounts left unchanged.", file=sys.stderr)
    return 0


def warm_voice_prompts(args: argparse.Namespace) -> int:
    """Synthesise every spoken prompt once so callers never wait for the voice service."""
    from raahat.application.ai.registry import build_providers
    from raahat.application.voicecall import script

    voice = build_providers(get_settings()).voice
    if voice is None or not voice.configured:
        print("Speech is not configured (GNANI_API_KEY_TTS_STT)", file=sys.stderr)
        return 1
    failures = 0
    keys = [*script.STEPS, "done", "retry"]
    jobs = [(line.language, line.spoken) for line in script.opening()]
    jobs += [(lang, script.line(lang, key).spoken) for lang in sorted(script.SUPPORTED) for key in keys]
    for language, spoken in jobs:
        try:
            voice.synthesize(spoken, language=language)
        except ProviderError as exc:
            failures += 1
            print(f"{language}: {exc}", file=sys.stderr)
    print(f"{len(jobs) - failures} of {len(jobs)} prompts ready.")
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m raahat.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="Create an administrator account")
    admin.add_argument("--username", required=True)
    admin.add_argument("--full-name", required=True)
    admin.add_argument("--password-stdin", action="store_true", help="Read the password from standard input")
    admin.set_defaults(handler=create_admin)

    provision = commands.add_parser(
        "provision-accounts", help="Create state and district control room accounts (CSV of passwords on stdout)"
    )
    provision.add_argument("--all", action="store_true", help="National, every state and every district")
    provision.add_argument("--national", action="store_true", help="The national administration account")
    provision.add_argument("--states", help="Comma-separated LGD state codes, e.g. 32 for Kerala")
    provision.add_argument("--no-districts", action="store_true", help="State accounts only")
    provision.add_argument("--reset", action="store_true", help="Issue new passwords for existing accounts too")
    provision.set_defaults(handler=provision_accounts)

    reset = commands.add_parser("reset-password", help="Set a user's password and end their sessions")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password-stdin", action="store_true")
    reset.set_defaults(handler=reset_password)

    landmarks = commands.add_parser("import-landmarks", help="Import OpenStreetMap landmarks for an area")
    landmarks.add_argument("--bbox", required=True, help="SOUTH,WEST,NORTH,EAST (at most 1 square degree)")
    landmarks.add_argument("--overpass-url", default="https://overpass-api.de/api/interpreter")
    landmarks.set_defaults(handler=import_landmarks)

    warm = commands.add_parser("warm-voice-prompts", help="Synthesise the voice call prompts in every language")
    warm.set_defaults(handler=warm_voice_prompts)

    check = commands.add_parser("check-config", help="Show which settings are present (no secrets printed)")
    check.set_defaults(handler=check_config)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
