"""Run the API server.

    python -m raahat.serve

One process (rate limits, the event listener and the connection pool are
per process; see RESOURCE_BUDGET.md). Listens on 127.0.0.1 unless HOST says
otherwise, because the public tunnel connects locally.

Graceful shutdown is bounded: open event streams never finish on their own,
so without a limit the server would wait for them indefinitely on stop.
"""
from __future__ import annotations

import os

import uvicorn

from raahat.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "raahat.api.app:app_factory",
        factory=True,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        workers=1,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=False,  # the application writes its own structured access log
        proxy_headers=settings.trust_forwarded_headers,
        forwarded_allow_ips="127.0.0.1" if settings.trust_forwarded_headers else None,
        timeout_graceful_shutdown=5,
        timeout_keep_alive=30,
        limit_concurrency=200,
        server_header=False,
    )


if __name__ == "__main__":
    main()
