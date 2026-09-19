#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import websockets' >/dev/null 2>&1; then
    .venv/bin/python -m pip install --index-url https://pypi.org/simple -r requirements.txt
fi
exec .venv/bin/python server.py
