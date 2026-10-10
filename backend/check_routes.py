"""Confirms the /api/v1 routes are registered on the app that `uvicorn backend.app.main:app` serves.
Run from the project root:   py -m backend.check_routes
Loads the app without starting a server. Exit code 1 if any route is missing."""
from __future__ import annotations

import sys

from .app import main

EXPECTED = ["/api/v1/health", "/api/v1/dashboard/summary", "/api/v1/warnings", "/api/v1/warnings/{warning_id}",
            "/api/v1/households", "/api/v1/households/{installation}"]


def run() -> int:
    app = main.app
    print(f"main.py loaded from: {main.__file__}")
    print(f"app version:         {app.version}   (this code is 1.1.0; anything else is an older copy)")
    registered = {r.path: sorted(r.methods or []) for r in app.routes if hasattr(r, "methods")}
    print("\napp.routes under /api/v1:")
    for path, methods in sorted(registered.items()):
        if path.startswith("/api/v1"):
            print(f"  {path}  {methods}")
    in_openapi = set(app.openapi()["paths"])
    missing = [p for p in EXPECTED if p not in registered or p not in in_openapi]
    print("\nMISSING: " + ", ".join(missing) if missing else "\nAll six /api/v1 routes are registered and in OpenAPI.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(run())
