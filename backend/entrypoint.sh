#!/bin/sh
set -e

# Run database migrations
echo "==> Running database migrations with Alembic..."
alembic upgrade head
echo "==> Database migrations applied successfully."

# If arguments are provided to the container, execute them; otherwise start uvicorn
if [ "$#" -gt 0 ]; then
    exec "$@"
else
    echo "==> Starting FastAPI application on 0.0.0.0:8000..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
