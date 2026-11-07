# Lessons

A distilled reasoning library, not a log. `PROJECT_PLAN.md`'s Log records
*what happened, in order* — this file records *what would help on a
different task*, retrievable by relevance instead of by reading
chronologically.

Inspired by the ReasoningBank pattern (Ouyang et al., "ReasoningBank:
Scaling Agent Self-Evolving with Reasoning Memory," arXiv:2509.25140) and
the post-run half of what runtime tools like ReasonBlocks do — extract a
reusable lesson after a task, retrieve the relevant one before the next.
This file replicates the distill-and-retrieve idea; it can't replicate
mid-run interception, which needs a runtime wrapper, not a markdown file.

## What belongs here

A lesson is **generalizable** — it should plausibly help on a task in a
*different* part of the codebase, or even a different project entirely.
If a note only makes sense re-reading this exact task's diff, it belongs
in `PROJECT_PLAN.md`'s Log, not here.

Good lesson: "HF's `Cache.update()` must return `(k, v)` for the current
layer only, not the accumulated cache — easy to get backwards."

Not a lesson (belongs in the Log instead): "Implemented `SimpleKVCache` in
`minigen/cache.py`."

## Format

Each entry: a short title, then 2-4 lines — what happened, what the
generalizable takeaway is, and where it applies. Keep entries short; a
lesson that takes a paragraph to state usually hasn't been distilled
enough yet.

Order: newest first, so skimming from the top surfaces recent lessons
first without needing to search.

---

## Browser EventSource Lacks Custom Header Support; Authenticate SSE via Query Parameter
- What happened: The web console failed to establish a live event stream because `new EventSource("/api/v1/events/stream")` cannot set custom HTTP headers (`X-Dispatcher-Id`), triggering a 401 Unauthorized rejection from the backend.
- Takeaway: Standard browser `EventSource` (and WebSocket) APIs cannot transmit arbitrary request headers. Endpoints using dependency injection for authentication must accept credentials from either HTTP headers or URL query parameters (`?dispatcher_id=...` or `?token=...`).
- Applies to: Server-Sent Events (SSE), WebSockets, and any browser-native streaming APIs.

## Compute Pairwise Clustering Metrics via Cluster Contingency Counters, Not $O(N^2)$ Loops
- What happened: Computing pairwise false merge and missed duplicate rates using nested $O(N^2)$ loops across $N=1,000$ reports scaled to $5 \times 10^8$ operations inside a $B=1,000$ paired bootstrap loop, hanging the evaluation runner.
- Takeaway: Calculate pairwise cluster combinations using cluster size contingency tables ($\binom{n}{2} = n(n-1)/2$). Intra- and inter-cluster pairs count in $O(N)$ time, reducing bootstrap runtime from minutes to milliseconds.
- Applies to: Entity resolution, coreference evaluation, clustering metrics, and any pairwise bootstrap resampling routine.

## Repository Protocols Belong in the Consuming Boundary, Not the Concrete Adapter
- What happened: Defining a `CallbackJobRepository` protocol in `infrastructure/database/repositories/callback.py` caused a circular import when `telephony/scheduler.py` imported the repository protocol while the repository module imported domain entities from `telephony/models.py`.
- Takeaway: Place repository and integration protocols in the consuming/domain layer (`src/.../telephony/repository.py`), letting concrete database adapters implement the protocol without creating backward dependency cycles.
- Applies to: Python architecture following Dependency Inversion across domain and persistence layers.

## Testing Long-Lived Streaming Responses in ASGI/FastAPI Requires Bounded Iteration
- What happened: `httpx.ASGITransport` runs ASGI applications to completion (`more_body=False`) before resolving the `Response` object in `AsyncClient.stream()` and `TestClient.get()`. Infinite streaming loops (such as SSE streams waiting on unbounded async pub/sub queues) hang in ASGI transports unless the generator explicitly supports terminating after a finite batch.
- Takeaway: Supply an optional `max_events` / `timeout` parameter to SSE generator routes. In production, `max_events=None` streams indefinitely; in ASGI test environments, specifying `max_events=N` yields $N$ events and terminates gracefully without hanging the transport.
- Applies to: FastAPI / Starlette SSE streaming, pub/sub broadcaster testing, and `httpx.ASGITransport`.

## In-Memory Test Doubles Must Not Tie-Break Chronological Order by Random UUIDs
- What happened: Sorting events in an in-memory repository by `(created_at, str(id))` scrambled the sequence of events recorded in rapid succession (with identical sub-millisecond timestamps), causing cryptographic hash chains to appear broken because the genesis event was sorted after subsequent events.
- Takeaway: For in-memory repositories testing sequential or chained event logs, preserve list insertion order (or assign an explicit monotonic sequence) rather than sorting on `(created_at, uuid)` where timestamps can collide.
- Applies to: In-memory test repositories, event-sourcing doubles, and audit log verification.

## Handling Both WKTElement and WKBElement in PostGIS Deserialization Routines
- What happened: GeoAlchemy2's `WKTElement` stores spatial text in its `.data` attribute as `str`, while `WKBElement` stores binary representation in `.data` as `bytes`. Assuming `.data` is always raw EWKB bytes caused `bytes(str)` to raise `TypeError: string argument without an encoding` when reading back an entity immediately after flush.
- Takeaway: Check `isinstance(raw_data.data, str)` first; if true and contains `"POINT"`, parse directly via WKT rather than coercing to bytes. Only unpack binary EWKB if `.data` is already `bytes`.
- Applies to: GeoAlchemy2 / PostGIS model repositories and geometry parsing helpers.

## Explicit Type Imports for Pydantic v2 Models with Future Annotations
- What happened: Under `from __future__ import annotations`, omitting runtime imports for types used in Pydantic models (such as `datetime` or `typing.Any`) passed module loading but raised `PydanticUserError: class is not fully defined; you should define X, then call Model.model_rebuild()` when FastAPI generated OpenAPI route response schemas.
- Takeaway: Even with postponed annotation evaluation, Pydantic v2 evaluates type hints at schema generation time using the declaring module's global namespace; every type referenced in request/response models must be explicitly imported in that file.
- Applies to: FastAPI and Pydantic v2 codebases using `from __future__ import annotations`.

## Explicit Intermediate Flushing for Independent Foreign-Key Dependent Models
- What happened: Inserting a new parent entity (`IncidentModel`) and a child link model (`IncidentLinkModel`) in the same session without an explicit ORM `relationship()` caused an `IntegrityError: ForeignKeyViolation` because SQLAlchemy's topological sort had no dependency edge to order the INSERTs.
- Takeaway: When two SQLAlchemy models share a foreign key relationship that is not mapped by an explicit ORM `relationship()` property, call `session.flush()` immediately after adding the parent entity before adding child entities referencing its generated UUID.
- Applies to: SQLAlchemy 2.0 applications with declarative models without back-populating relationships.

## Domain Protocol Location for Dependency Inversion and Circular Import Prevention
- What happened: Placing repository interface protocols in `infrastructure/` caused circular imports when `domain/` services imported the interface and `infrastructure/` imported domain entities from the domain package `__init__.py`.
- Takeaway: By strict dependency inversion, repository Protocols and pure-Python in-memory implementations belong in the `domain/` layer (e.g. `domain/evidence/repository.py`). The `infrastructure/` layer implements the protocol and can re-export it. Domain services never import from `infrastructure/`.
- Applies to: Clean Architecture / DDD Python codebases, protocol definitions, and test doubles.

## Preserving Client Event Timestamps Distinctly in Offline-First Sync Ingestion
- What happened: In offline synchronization protocols, batch events arrive with delay or out of order relative to wall-clock server receipt time. Overwriting or conflating event generation time with server arrival time skews disaster intelligence timelines.
- Takeaway: Maintain two distinct timestamp fields: `client_created_at` (immutable client-asserted observation timestamp) and `received_at` (server transaction receipt timestamp). Rely on monotonic sequence counters (`from_sequence..to_sequence`) and composite keys (`device_id:seq`) for idempotency rather than timestamps.
- Applies to: Offline-first data pipelines, mobile/field sync endpoints, and distributed event ingestion.

## SQLite In-Memory Shared Connection Concurrency in Python
- What happened: When multiple worker threads begin transactions via `BEGIN IMMEDIATE;` on a shared in-memory SQLite connection (`check_same_thread=False`), SQLite raises `sqlite3.OperationalError: cannot start a transaction within a transaction`.
- Takeaway: For thread-safe SQLite connection managers (especially with `:memory:` testing or multi-worker offline queues), guard transaction blocks with a `threading.Lock()` to serialize transaction boundaries across threads.
- Applies to: Any Python project using SQLite with multithreaded workers or shared in-memory test databases.

## Parsing PostGIS EWKB Points in Pure Python without Shapely
- What happened: `geoalchemy2.shape.to_shape()` raises `ModuleNotFoundError: No module named 'shapely'` unless `shapely` is installed as an optional dependency.
- Takeaway: For extracting latitude/longitude from PostGIS `geography(Point, 4326)` columns, parse EWKB bytes using Python's standard library `struct.unpack(endian + 'dd', raw[offset:offset+16])` (where `offset = 9` if SRID flag `0x20000000` is present, else `5`), avoiding heavy C-extension dependencies.
- Applies to: Python applications reading PostGIS point geometries via SQLAlchemy / GeoAlchemy2.

## PostGIS Geography vs Geometry for Bounding Box Containment
- What happened: `ST_Within` operates on `geometry` with matching SRIDs and does not accept `geography` directly (`function st_geometry(geography) does not exist`). `ST_MakeEnvelope` returns a `geometry(Polygon, 4326)`.
- Takeaway: For bounding box checks on a `geography(Point, 4326)` column, cast the column to geometry: `ST_Within(location::geometry, ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326))` which uses the spatial index and exact polygon containment. For distance-radius checks in metres, use `ST_DWithin(location, ST_MakePoint(lon, lat)::geography, radius_m)`.
- Applies to: Any PostGIS project storing coordinates as `geography` while supporting spatial bounding boxes.

## Python stdlib `audioop` deprecation in 3.11+ (removal in 3.13)
- What happened: `import audioop` triggers a `DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13` on modern Python versions.
- Takeaway: For RMS or amplitude calculation on 16-bit linear PCM audio, use `struct.unpack(f"<{n}h", bytes)` with `math.sqrt(sum(s*s for s in samples)/n)` instead of `audioop.rms` for future-proof, warning-free stdlib code.
- Applies to: Any Python project handling raw PCM audio processing without heavy external dependencies.

## SQLAlchemy 2.0 `CursorResult.rowcount` typing with mypy
- What happened: In SQLAlchemy 2.0, `session.execute(update(...))` is statically typed as returning `Result[Any]`, which does not expose `rowcount` under strict mypy checks (`"Result[Any]" has no attribute "rowcount"`).
- Takeaway: Import `from sqlalchemy.engine import CursorResult` and assert `isinstance(result, CursorResult)` to safely access `result.rowcount`.
- Applies to: Any project using SQLAlchemy 2.0 with mypy type checking on DML statements.

## GeoAlchemy2 duplicate spatial index creation with Alembic
- What happened: GeoAlchemy2's `Geometry` and `Geography` types default to `spatial_index=True`. When models also define an explicit GIST index in `__table_args__`, Alembic's autogenerated migration attempts to create the index twice, failing with `relation already exists`.
- Takeaway: Set `spatial_index=False` on `Geometry`/`Geography` columns when declaring explicit named indexes in `__table_args__`.
- Applies to: Any SQLAlchemy project using GeoAlchemy2 and Alembic migrations.

## SQLAlchemy column name shadowing `relationship`
- What happened: In `IncidentReportModel`, a column named `relationship` (`relationship: Mapped[str] = mapped_column(...)`) shadowed the `relationship` function imported from `sqlalchemy.orm` within the class body, causing subsequent relationship declarations to fail with `'MappedColumn' object is not callable`.
- Takeaway: Alias `from sqlalchemy.orm import relationship as sa_relationship` whenever a table model has a domain field named `relationship`.
- Applies to: Relational database models modeling link or association types.

## Pytest entrypoint collisions from ambient ROS environment
- What happened: pytest failed during initial collection because `PYTHONPATH` contained `/opt/ros/jazzy/lib/python3.12/site-packages`, triggering setuptools entrypoint loading for `launch_testing` which failed on missing dependencies.
- Takeaway: In hybrid development environments where ROS or robotics paths leak into `PYTHONPATH`, pytest must be shielded with `addopts = "-p no:launch_testing"` in `pyproject.toml` and pytest invoked with clean `PYTHONPATH`.
- Applies to: Any Python project running tests on systems with ROS or other system-level pytest plugin injectors.
