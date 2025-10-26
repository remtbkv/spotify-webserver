#!/usr/bin/env python3
"""Helper runner to start the Flask app locally from the repository root.

Use this script when developing locally so imports resolve the same way
they do on the deployed server. From the repo root run:

  python run_local.py

This avoids common import issues when executing files inside the `app/`
folder directly (which can break package imports like `app.spotify_client`).
"""
import os
import sys

# Ensure repository root is on sys.path so `import app.*` works consistently
ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.main import app

if __name__ == "__main__":
    # Allow overriding host/port via env for flexibility
    host = os.getenv('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_RUN_PORT', '9090'))
    debug = os.getenv('FLASK_DEBUG', '1') not in ('0', 'false', 'False')
    app.run(host=host, port=port, debug=debug)
