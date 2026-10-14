# app.py — Flask web application for the SafeParse compiler.
#
# WHAT: Provides web pages for user registration, login, compiling binary format
#       specs into naive and optimized C parsers, viewing history, and viewing
#       fuzzing/benchmark results.
# WHY:  Allows developers to easily test the SafeParse compiler in their browser
#       and track generated C parser artifacts in an SQLite database.

import os
import sys
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

# Ensure the project root is in sys.path so we can import safeparse.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from safeparse.compiler import compile_spec
from webapp.db import get_db, close_db, init_db


# ---------------------------------------------------------------------------
# Flask Application Setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Secret key for session cookie signing.
# Uses FLASK_SECRET_KEY environment variable with a development fallback.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret-key-do-not-use-in-production"
)

# Default path for the SQLite database.
app.config["DATABASE"] = os.path.join(PROJECT_ROOT, "safeparse.db")

# Register teardown function to clean up database connections.
app.teardown_appcontext(close_db)


# Default spec text for the compile page.
DEFAULT_UDP_SPEC = """format UdpHeader {
    src_port:  u16
    dst_port:  u16
    length:    u16
    checksum:  u16
    payload:   bytes[length - 8]
}"""


# ---------------------------------------------------------------------------
# Authentication Decorator
# ---------------------------------------------------------------------------

def login_required(view_function):
    """
    Decorator that requires a user to be logged in to view a page.

    WHAT: Checks whether 'user_id' exists in the Flask session.
    WHY:  Prevents unauthorized access to private pages like compile,
          history, and results.
    """
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)
    return wrapped_view


# ---------------------------------------------------------------------------
# Authentication Routes (Register, Login, Logout)
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """
    Redirect the root URL to the compile page or login page.

    WHAT: Inspects login state and sends the user to the right place.
    WHY:  Provides a natural entry point for the website.
    """
    if "user_id" in session:
        return redirect(url_for("compile_page"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Register a new user account with role 'developer'.

    WHAT: Validates username and password, hashes the password, and
          inserts a new row into the users table.
    WHY:  Gives new developers an account so they can use SafeParse.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # Check for empty username or password.
        if not username or not password:
            flash("Username and password cannot be empty.")
            return render_template("register.html")

        db_conn = get_db()

        # Check if the username already exists.
        existing_user = db_conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if existing_user is not None:
            flash("Username already taken. Please choose another.")
            return render_template("register.html")

        # Hash the password for secure storage.
        hashed_password = generate_password_hash(password)

        # Insert new user with default role 'developer'.
        db_conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'developer')",
            (username, hashed_password)
        )
        db_conn.commit()

        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Log in an existing user and start a session.

    WHAT: Checks username and password against the database.
    WHY:  Authenticates the user and sets session variables.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db_conn = get_db()
        user_row = db_conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        # Check credentials using werkzeug's secure hash verification.
        if user_row is None or not check_password_hash(user_row["password_hash"], password):
            # One generic error message so attackers cannot guess usernames.
            flash("Invalid username or password.")
            return render_template("login.html")

        # Set session data.
        session.clear()
        session["user_id"] = user_row["id"]
        session["username"] = user_row["username"]
        session["role"] = user_row["role"]

        return redirect(url_for("compile_page"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """
    Log out the current user and clear the session.

    WHAT: Empties the session dictionary and redirects to login.
    WHY:  Allows the user to safely end their authenticated session.
    """
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Compiler Route
# ---------------------------------------------------------------------------

@app.route("/compile", methods=["GET", "POST"])
@login_required
def compile_page():
    """
    Display spec compiler interface and handle compilation requests.

    WHAT: Compiles the spec using safeparse.compiler.compile_spec in both
          'naive' and 'optimized' modes, saves the spec and parsers into the
          database, and shows the generated C code side by side.
    WHY:  Main feature of the web app; lets users see the difference between
          naive and optimized bounds-checking.
    """
    if request.method == "POST":
        spec_text = request.form.get("spec_text", "").strip()

        if not spec_text:
            flash("Please enter a format specification.")
            return render_template("compile.html", spec_text=spec_text)

        # Call the existing compiler function for BOTH variants.
        naive_result = compile_spec(spec_text, mode="naive")
        opt_result = compile_spec(spec_text, mode="optimized")

        # If the spec is invalid, show compiler errors and save nothing.
        if not naive_result["success"]:
            return render_template(
                "compile.html",
                spec_text=spec_text,
                compiler_errors=naive_result["errors"]
            )

        # Valid spec: save to database.
        format_name = naive_result["format_name"]
        user_id = session["user_id"]
        db_conn = get_db()

        # 1. Save spec record.
        cursor = db_conn.execute(
            "INSERT INTO specs (user_id, name, spec_text) VALUES (?, ?, ?)",
            (user_id, format_name, spec_text)
        )
        spec_id = cursor.lastrowid

        # 2. Save naive parser record.
        db_conn.execute(
            "INSERT INTO generated_parsers (spec_id, variant, c_code) VALUES (?, 'naive', ?)",
            (spec_id, naive_result["c_code"])
        )

        # 3. Save optimized parser record.
        db_conn.execute(
            "INSERT INTO generated_parsers (spec_id, variant, c_code) VALUES (?, 'optimized', ?)",
            (spec_id, opt_result["c_code"])
        )
        db_conn.commit()

        return render_template(
            "compile.html",
            spec_text=spec_text,
            format_name=format_name,
            naive_c_code=naive_result["c_code"],
            opt_c_code=opt_result["c_code"],
            compilation_success=True
        )

    # GET request: show default example spec.
    return render_template("compile.html", spec_text=DEFAULT_UDP_SPEC)


# ---------------------------------------------------------------------------
# History and Detail Routes
# ---------------------------------------------------------------------------

@app.route("/history")
@login_required
def history():
    """
    List past specifications and generated parsers.

    WHAT: Queries the specs table. Developers see only their own specs;
          admins see all specs along with the author username.
    WHY:  Provides history tracking and enforces role-based access control.
    """
    db_conn = get_db()
    current_role = session.get("role")
    current_user_id = session.get("user_id")

    if current_role == "admin":
        # Admin sees all specs with author usernames.
        specs_query = """
            SELECT specs.id, specs.name, specs.created_at, users.username
            FROM specs
            JOIN users ON specs.user_id = users.id
            ORDER BY specs.id DESC
        """
        spec_rows = db_conn.execute(specs_query).fetchall()
    else:
        # Developer sees only their own specs.
        specs_query = """
            SELECT specs.id, specs.name, specs.created_at
            FROM specs
            WHERE specs.user_id = ?
            ORDER BY specs.id DESC
        """
        spec_rows = db_conn.execute(specs_query, (current_user_id,)).fetchall()

    return render_template(
        "history.html",
        specs=spec_rows,
        is_admin=(current_role == "admin")
    )


@app.route("/history/<int:spec_id>")
@login_required
def history_detail(spec_id):
    """
    Display details of a single specification and its generated C parsers.

    WHAT: Checks ownership authorization, fetches the spec and both parser
          variants, and renders them.
    WHY:  Users need to be able to view previously generated C code, while
          ensuring users cannot view other users' code unless they are admin.
    """
    db_conn = get_db()
    current_role = session.get("role")
    current_user_id = session.get("user_id")

    # Fetch the spec.
    spec_row = db_conn.execute(
        "SELECT specs.id, specs.user_id, specs.name, specs.spec_text, specs.created_at, users.username "
        "FROM specs JOIN users ON specs.user_id = users.id WHERE specs.id = ?",
        (spec_id,)
    ).fetchone()

    if spec_row is None:
        abort(404)

    # Authorization check: only owner or admin can view this record.
    if spec_row["user_id"] != current_user_id and current_role != "admin":
        abort(403)

    # Fetch both generated parsers (naive and optimized).
    parsers = db_conn.execute(
        "SELECT variant, c_code FROM generated_parsers WHERE spec_id = ?",
        (spec_id,)
    ).fetchall()

    naive_c_code = ""
    opt_c_code = ""
    for parser_row in parsers:
        if parser_row["variant"] == "naive":
            naive_c_code = parser_row["c_code"]
        elif parser_row["variant"] == "optimized":
            opt_c_code = parser_row["c_code"]

    return render_template(
        "history_detail.html",
        spec=spec_row,
        naive_c_code=naive_c_code,
        opt_c_code=opt_c_code
    )


# ---------------------------------------------------------------------------
# Results Route
# ---------------------------------------------------------------------------

@app.route("/results")
@login_required
def results():
    """
    Display evaluation results (fuzzing and benchmark performance).

    WHAT: Queries the test_runs table joined with generated_parsers and specs.
          If no tests have been run, displays a friendly empty-state message.
    WHY:  Displays real benchmark and fuzzing results without ever inventing
          fake or seeded numbers.
    """
    db_conn = get_db()
    results_query = """
        SELECT
            specs.name AS spec_name,
            generated_parsers.variant AS variant,
            test_runs.fuzz_duration_sec,
            test_runs.crashes_found,
            test_runs.avg_speed_ns
        FROM test_runs
        JOIN generated_parsers ON test_runs.parser_id = generated_parsers.id
        JOIN specs ON generated_parsers.spec_id = specs.id
        ORDER BY test_runs.id DESC
    """
    test_run_rows = db_conn.execute(results_query).fetchall()

    return render_template("results.html", test_runs=test_run_rows)


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    print("Starting SafeParse web application on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)
