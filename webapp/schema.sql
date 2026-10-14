-- schema.sql — Database schema for the SafeParse web application.
--
-- WHAT: Creates the four required tables for users, specs, parsers, and test runs.
-- WHY:  SQLite needs tables to store user credentials, format specifications,
--       the generated C parser code, and any benchmark or fuzzing results.

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'developer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS specs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT,
    spec_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generated_parsers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id INTEGER NOT NULL REFERENCES specs(id),
    variant TEXT NOT NULL,
    c_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parser_id INTEGER NOT NULL REFERENCES generated_parsers(id),
    fuzz_duration_sec INTEGER,
    crashes_found INTEGER,
    avg_speed_ns REAL
);
