#!/usr/bin/env bash

# 1) Frontend-Dev-Server starten
cd frontend
npm install
npm run dev &         # <-- startet vite mit Hot-Reload
FRONTEND_PID=$!
if [ $? -ne 0 ]; then
    echo "Failed to restore frontend npm packages"
    exit $?
fi

cd ..
. ./scripts/loadenv.sh

echo ""
echo "Starting backend"
echo ""
./.venv/bin/python -m quart run --port=50505 --host=127.0.0.1 --reload
if [ $? -ne 0 ]; then
    echo "Failed to start backend"
    exit $?
fi

# Wenn Du magst, beendest Du zeilenweise auch den Frontend-Server wieder:
kill $FRONTEND_PID
