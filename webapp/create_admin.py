# create_admin.py — Command-line script to create an administrator user.
#
# WHAT: Prompts for a username and password from the terminal and inserts
#       an admin user into the SQLite database.
# WHY:  Admins have special permissions (e.g. viewing all users' specs in history).
#       This script provides a simple way to set up the first admin.
#
# Usage:
#   python webapp/create_admin.py

import os
import sys
import getpass
from werkzeug.security import generate_password_hash

# Ensure the project root is in sys.path so we can import webapp modules.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from webapp.db import get_db, init_db


def prompt_for_credentials():
    """
    Prompt the user to enter a username and password at the terminal.

    WHAT: Reads username via input() and password via getpass.getpass()
          (which hides keystrokes for privacy).
    WHY:  Keeps passwords from showing on the terminal screen.
    """
    username = input("Enter admin username: ").strip()
    if not username:
        print("Error: Username cannot be empty.")
        sys.exit(1)

    # Use getpass to securely read password without terminal echo.
    # Fallback to standard input if running in an environment without tty.
    try:
        password = getpass.getpass("Enter admin password: ").strip()
    except Exception:
        password = input("Enter admin password: ").strip()

    if not password:
        print("Error: Password cannot be empty.")
        sys.exit(1)

    return username, password


def create_admin_user(username, password):
    """
    Insert or promote a user to the 'admin' role in the database.

    WHAT: Hashes the password and writes the user record into the users table.
    WHY:  Passwords must always be hashed before storage for security.
    """
    # Make sure the database and tables exist.
    init_db()

    db_conn = get_db()

    # Check if the username already exists.
    existing_user = db_conn.execute(
        "SELECT id, role FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    hashed_password = generate_password_hash(password)

    if existing_user is not None:
        # Update existing user's password and promote to admin.
        db_conn.execute(
            "UPDATE users SET password_hash = ?, role = 'admin' WHERE id = ?",
            (hashed_password, existing_user["id"])
        )
        db_conn.commit()
        db_conn.close()
        print("User '{}' already existed. Successfully updated and promoted to admin.".format(username))
    else:
        # Create brand new admin user.
        db_conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (username, hashed_password)
        )
        db_conn.commit()
        db_conn.close()
        print("Admin user '{}' created successfully!".format(username))


def main():
    """
    Main function for the create_admin CLI script.

    WHAT: Collects credentials from terminal and creates the admin account.
    WHY:  Standard entry point when running the script directly.
    """
    print("--- SafeParse Administrator Account Setup ---")
    username, password = prompt_for_credentials()
    create_admin_user(username, password)


if __name__ == "__main__":
    main()
