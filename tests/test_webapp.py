# test_webapp.py — Integration tests for the SafeParse Flask web application.
#
# WHAT: Tests user registration, authentication, spec compilation,
#       history isolation, administrator visibility, and results reporting
#       using Flask's test client and an isolated temporary SQLite database.
# WHY:  Ensures that the web application works correctly and securely
#       before deployment.
#
# Run with:  pytest tests/test_webapp.py -v

import os
import pytest
from werkzeug.security import generate_password_hash

from webapp.app import app
from webapp.db import init_db, get_db


@pytest.fixture
def client(tmp_path):
    """
    Create a test client configured with a temporary database.

    WHAT: Points app.config['DATABASE'] to a clean SQLite database inside
          a temporary folder, initializes the schema, and yields a test client.
    WHY:  Keeps test data isolated so tests never affect the real database.
    """
    db_file = tmp_path / "test_safeparse.db"
    db_path = str(db_file)

    app.config["DATABASE"] = db_path
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"

    # Initialize the database schema for the test.
    with app.app_context():
        init_db(db_path)

    with app.test_client() as test_client:
        yield test_client


def register_user(client, username, password):
    """Helper to register a user account."""
    return client.post(
        "/register",
        data={"username": username, "password": password},
        follow_redirects=True
    )


def login_user(client, username, password):
    """Helper to log in a user account."""
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_register(client):
    """Registering a new account should store the hashed password with developer role."""
    response = register_user(client, "alice", "secret123")
    assert response.status_code == 200
    assert b"Registration successful" in response.data

    # Check database directly.
    with app.app_context():
        db_conn = get_db()
        user = db_conn.execute(
            "SELECT username, role, password_hash FROM users WHERE username = ?",
            ("alice",)
        ).fetchone()
        assert user is not None
        assert user["username"] == "alice"
        assert user["role"] == "developer"
        # Password must be hashed, never stored in plain text.
        assert user["password_hash"] != "secret123"

    # Duplicate registration should be rejected.
    dup_response = register_user(client, "alice", "secret456")
    assert b"already taken" in dup_response.data


def test_login_and_logout(client):
    """Logging in with valid credentials should succeed; logging out clears the session."""
    register_user(client, "bob", "mypassword")

    # Bad login attempt.
    bad_login = login_user(client, "bob", "wrongpassword")
    assert b"Invalid username or password" in bad_login.data

    # Good login attempt.
    good_login = login_user(client, "bob", "mypassword")
    assert b"Compile" in good_login.data
    assert b"bob" in good_login.data

    # Log out.
    logout_response = client.get("/logout", follow_redirects=True)
    assert b"logged out" in logout_response.data


def test_compile_success(client):
    """Compiling a valid spec should save the spec and both parser variants."""
    register_user(client, "charlie", "pass123")
    login_user(client, "charlie", "pass123")

    spec_code = "format TestPkt { src: u16 dst: u16 }"
    response = client.post(
        "/compile",
        data={"spec_text": spec_code},
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Success!" in response.data
    assert b"Naive Parser" in response.data
    assert b"Optimized Parser" in response.data
    assert b"parse_TestPkt" in response.data

    # Check that database records were created.
    with app.app_context():
        db_conn = get_db()
        spec = db_conn.execute("SELECT id, name FROM specs WHERE name = 'TestPkt'").fetchone()
        assert spec is not None

        parsers = db_conn.execute(
            "SELECT variant, c_code FROM generated_parsers WHERE spec_id = ?",
            (spec["id"],)
        ).fetchall()
        assert len(parsers) == 2
        variants = [p["variant"] for p in parsers]
        assert "naive" in variants
        assert "optimized" in variants


def test_compile_invalid_spec(client):
    """An invalid spec should display compiler error messages and save nothing."""
    register_user(client, "dave", "pass123")
    login_user(client, "dave", "pass123")

    # Spec has an unknown type 'u64'
    bad_spec = "format BadPkt { data: u64 }"
    response = client.post(
        "/compile",
        data={"spec_text": bad_spec},
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Compilation Failed" in response.data
    assert b"unknown type" in response.data
    assert b"u64" in response.data

    # Ensure nothing was saved into the database.
    with app.app_context():
        db_conn = get_db()
        count = db_conn.execute("SELECT COUNT(*) AS count FROM specs").fetchone()["count"]
        assert count == 0


def test_history_isolation_between_users(client):
    """Developers should only see their own specs, not other users' specs."""
    # Create two developer accounts.
    register_user(client, "user_one", "pass1")
    register_user(client, "user_two", "pass2")

    # user_one compiles a spec.
    login_user(client, "user_one", "pass1")
    client.post("/compile", data={"spec_text": "format OneHdr { x: u8 }"})
    client.get("/logout")

    # user_two compiles a different spec.
    login_user(client, "user_two", "pass2")
    client.post("/compile", data={"spec_text": "format TwoHdr { y: u16 }"})

    # user_two visits history.
    history_resp = client.get("/history")
    assert b"TwoHdr" in history_resp.data
    assert b"OneHdr" not in history_resp.data

    # user_two tries to open user_one's spec directly.
    with app.app_context():
        db_conn = get_db()
        spec_one = db_conn.execute("SELECT id FROM specs WHERE name = 'OneHdr'").fetchone()

    detail_resp = client.get(f"/history/{spec_one['id']}")
    # Forbidden (403).
    assert detail_resp.status_code == 403


def test_admin_sees_all_history(client):
    """An administrator should see specifications from all users."""
    # Create a regular user and compile a spec.
    register_user(client, "user_three", "pass3")
    login_user(client, "user_three", "pass3")
    client.post("/compile", data={"spec_text": "format ThreeHdr { z: u32 }"})
    client.get("/logout")

    # Create an admin user manually in the database.
    with app.app_context():
        db_conn = get_db()
        db_conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("superadmin", generate_password_hash("adminpass"))
        )
        db_conn.commit()

    # Admin logs in and checks history.
    login_user(client, "superadmin", "adminpass")
    history_resp = client.get("/history")

    assert b"ThreeHdr" in history_resp.data
    assert b"user_three" in history_resp.data

    # Admin can open user_three's spec detail.
    with app.app_context():
        db_conn = get_db()
        spec_three = db_conn.execute("SELECT id FROM specs WHERE name = 'ThreeHdr'").fetchone()

    detail_resp = client.get(f"/history/{spec_three['id']}")
    assert detail_resp.status_code == 200
    assert b"ThreeHdr" in detail_resp.data


def test_results_empty_state(client):
    """Results page should display 'No evaluation results recorded yet' when test_runs is empty."""
    register_user(client, "eval_user", "pass123")
    login_user(client, "eval_user", "pass123")

    response = client.get("/results")
    assert response.status_code == 200
    assert b"No evaluation results recorded yet" in response.data
