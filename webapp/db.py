# db.py — Database connection and initialization helpers for SafeParse.
#
# WHAT: Manages SQLite database connections, schema setup, and cleanup.
# WHY:  Centralizes database access so the web app and admin tools can
#       share the same setup logic without duplicating connection code.

import sqlite3
import os
from flask import g, current_app, has_app_context


# Path to the schema.sql file in the same folder as this script.
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Default database filename.
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "safeparse.db"
)


def get_db(db_path=None):
    """
    Get or create an active SQLite connection.

    WHAT: Opens a connection to the SQLite database file and enables
          row-access by column name (Row factory) and foreign keys.
    WHY:  Within a Flask request, we reuse the same connection stored on 'g'
          so multiple queries do not open and close files repeatedly.
    """
    # If we are inside an active Flask request context, use g.
    if has_app_context():
        if "db" not in g:
            target_path = db_path
            if target_path is None:
                target_path = current_app.config.get("DATABASE", DEFAULT_DB_PATH)
            connection = sqlite3.connect(target_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            g.db = connection
        return g.db

    # Outside Flask request context (e.g. standalone scripts or tests).
    target_path = db_path
    if target_path is None:
        target_path = DEFAULT_DB_PATH
    connection = sqlite3.connect(target_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def close_db(error=None):
    """
    Close the database connection at the end of the request.

    WHAT: Retrieves the database connection from 'g' and closes it.
    WHY:  Prevents connection leaks and ensures file locks are released.
    """
    if has_app_context():
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()


def init_db(db_path=None):
    """
    Initialize the database using the schema.sql file.

    WHAT: Reads the SQL statements in schema.sql and runs them.
    WHY:  Ensures that all four tables (users, specs, generated_parsers,
          and test_runs) exist before the web app handles any requests.
    """
    with open(SCHEMA_PATH, "r") as schema_file:
        schema_sql = schema_file.read()

    connection = get_db(db_path)
    connection.executescript(schema_sql)
    connection.commit()

    # If this was a standalone connection outside Flask, close it.
    if not has_app_context():
        connection.close()
