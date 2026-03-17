#!/bin/bash

set -e
set -u

DB_NAME="${POSTHOG_PERSONS_DB_NAME:-posthog_persons}"

echo "Checking if database '${DB_NAME}' exists..."
DB_EXISTS=$(psql -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")

if [ -z "$DB_EXISTS" ]; then
    echo "Creating database '${DB_NAME}'..."
    psql -U "$POSTGRES_USER" -c "CREATE DATABASE ${DB_NAME};"
    psql -U "$POSTGRES_USER" -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO $POSTGRES_USER;"
    echo "Database '${DB_NAME}' created successfully"
else
    echo "Database '${DB_NAME}' already exists"
fi
