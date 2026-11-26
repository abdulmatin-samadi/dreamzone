#!/usr/bin/env bash
# One command to run everything: ./run.sh   (Ctrl+C stops both servers)
set -e
cd "$(dirname "$0")"
API_PORT=8010
(cd backend && . .venv/bin/activate && python manage.py migrate -v0 && python manage.py seed_demo >/dev/null)
(cd backend && . .venv/bin/activate && exec python manage.py runserver $API_PORT) &
API=$!
trap 'kill $API 2>/dev/null' EXIT INT TERM
cd frontend
[ -d node_modules ] || npm install
echo; echo "  Open: http://localhost:5173   (admin / Admin12345!  |  reception, teacher, student / Demo12345!)"; echo
VITE_PROXY_TARGET=http://localhost:$API_PORT npx vite --port 5173 --open
