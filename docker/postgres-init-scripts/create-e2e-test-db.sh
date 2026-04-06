#!/bin/bash

set -e
set -u

for db_name in posthog_e2e_test posthog_persons_e2e_test; do
    echo "Checking if database '$db_name' exists..."
    DB_EXISTS=$(psql -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$db_name'")

    if [ -z "$DB_EXISTS" ]; then
        echo "Creating database '$db_name'..."
        psql -U "$POSTGRES_USER" -c "CREATE DATABASE $db_name;"
        psql -U "$POSTGRES_USER" -c "GRANT ALL PRIVILEGES ON DATABASE $db_name TO $POSTGRES_USER;"
        echo "Database '$db_name' created successfully"
    else
        echo "Database '$db_name' already exists"
    fi
done
