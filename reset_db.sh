#!/bin/bash
# Database reset script for local development
# Usage: ./reset_db.sh

echo "Resetting database..."
psql postgres -c "DROP DATABASE IF EXISTS docecho;"
psql postgres -c "CREATE DATABASE docecho;"
rm -rf migrations/
flask db init
flask db migrate -m "initial_schema"
flask db upgrade
echo "Database reset complete!" 