import getpass
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("DATABASE_PATH", str(ROOT / "courses.db")))
DB.parent.mkdir(parents=True, exist_ok=True)


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        600000
    ).hex()


def create_user(username, password, role):
    username = username.strip()

    if (
        not username
        or role not in ("teacher", "student")
        or not 12 <= len(password) <= 128
    ):
        raise ValueError(
            "Use a username, teacher/student role, "
            "and a password between 12 and 128 characters."
        )

    salt = secrets.token_hex(16)

    with closing(connect()) as db, db:
        db.execute(
            """
            INSERT INTO users (username, password_hash, salt, role)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash(password, salt), salt, role)
        )


def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                subject TEXT NOT NULL,
                credits INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('teacher', 'student'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                expires_at INTEGER NOT NULL
            );
        """)
    starter_courses = [
        (
            "BIO 101 – Introduction to Biology",
            "Introduction to the basic principles of biology, including "
            "cells, genetics, evolution, and ecosystems.",
            "Science",
            3
        ),
        (
            "ENG 111 – English Composition",
            "Development of college-level writing, research, critical "
            "thinking, and communication skills.",
            "English",
            3
        ),
        (
            "MAT 136 – College Algebra",
            "Study of algebraic concepts including equations, functions, "
            "graphs, and problem-solving.",
            "Mathematics",
            3
        )
    ]

    with closing(connect()) as db, db:
        for course in starter_courses:
            db.execute(
                """
                INSERT INTO courses (name, description, subject, credits)
                SELECT ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM courses WHERE name = ?
                )
                """,
                (*course, course[0])
            )

    # Create initial accounts from environment variables, if provided.
    for role in ("teacher", "student"):
        prefix = role.upper()
        password = os.environ.get(prefix + "_PASSWORD")
        username = os.environ.get(prefix + "_USERNAME", role)

        if password:
            with closing(connect()) as db:
                exists = db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

            if not exists:
                create_user(username, password, role)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization"
        )
        self.end_headers()

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))

            if not 0 < length <= 10000:
                raise ValueError()

            data = json.loads(self.rfile.read(length))

            if not isinstance(data, dict):
                raise ValueError()

            return data

        except (ValueError, UnicodeDecodeError):
            self.send_json(400, {"error": "Invalid request."})
            return None

    def token_hash(self):
        header = self.headers.get("Authorization", "")

        if not header.startswith("Bearer "):
            return ""

        return hashlib.sha256(header[7:].encode()).hexdigest()

    def current_user(self):
        with closing(connect()) as db:
            row = db.execute(
                """
                SELECT users.id, users.username, users.role
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE token_hash = ? AND expires_at > ?
                """,
                (self.token_hash(), int(time.time()))
            ).fetchone()

            return dict(row) if row else None

    def require_teacher(self):
        user = self.current_user()

        if not user:
            self.send_json(401, {"error": "Please log in."})
            return False

        if user["role"] != "teacher":
            self.send_json(
                403,
                {"error": "Only teachers can change courses."}
            )
            return False

        return True

    def course_id(self):
        parts = urlparse(self.path).path.split("/")

        if (
            len(parts) == 4
            and parts[:3] == ["", "api", "courses"]
            and parts[3].isdigit()
        ):
            return int(parts[3])

        return None

    def read_course(self):
        data = self.read_json()

        if data is None:
            return None

        try:
            fields = [
                data[key].strip()
                for key in ("name", "description", "subject")
            ]
            credits = data["credits"]

            if (
                not all(fields)
                or type(credits) is not int
                or not 1 <= credits <= 20
            ):
                raise ValueError()

            return (*fields, credits)

        except (KeyError, AttributeError, ValueError):
            self.send_json(
                400,
                {
                    "error": (
                        "Fill in every field. Credits must be "
                        "a whole number from 1 to 20."
                    )
                }
            )
            return None

    def login(self):
        data = self.read_json()

        if data is None:
            return

        username = data.get("username")
        password = data.get("password")

        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or len(password) > 128
        ):
            self.send_json(
                400,
                {"error": "Enter a username and password."}
            )
            return

        with closing(connect()) as db, db:
            row = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip(),)
            ).fetchone()

            salt = row["salt"] if row else "00" * 16
            digest = password_hash(password, salt)

            if (
                not row
                or not hmac.compare_digest(digest, row["password_hash"])
            ):
                self.send_json(
                    401,
                    {"error": "Incorrect username or password."}
                )
                return

            token = secrets.token_urlsafe(32)

            db.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (int(time.time()),)
            )

            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    row["id"],
                    int(time.time()) + 28800
                )
            )

            self.send_json(
                200,
                {
                    "token": token,
                    "user": {
                        "id": row["id"],
                        "username": row["username"],
                        "role": row["role"]
                    }
                }
            )

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/me":
            user = self.current_user()

            if user:
                self.send_json(200, {"user": user})
            else:
                self.send_json(401, {"error": "Please log in."})

        elif path == "/api/courses":
            with closing(connect()) as db:
                rows = db.execute(
                    "SELECT * FROM courses ORDER BY id DESC"
                ).fetchall()

                self.send_json(200, [dict(row) for row in rows])

        elif self.course_id() is not None:
            with closing(connect()) as db:
                row = db.execute(
                    "SELECT * FROM courses WHERE id = ?",
                    (self.course_id(),)
                ).fetchone()

                if row:
                    self.send_json(200, dict(row))
                else:
                    self.send_json(404, {"error": "Course not found."})

        else:
            name = "index.html" if path == "/" else path.lstrip("/")

            allowed = {
                "index.html",
                "courses.html",
                "add-course.html",
                "course-details.html",
                "login.html",
                "login.js",
                "course-app.js",
                "script.js",
                "style.css"
            }

            if name not in allowed or not (ROOT / name).is_file():
                self.send_json(404, {"error": "Not found."})
                return

            body = (ROOT / name).read_bytes()

            mime = {
                ".html": "text/html",
                ".js": "text/javascript",
                ".css": "text/css"
            }

            self.send_response(200)
            self.send_header(
                "Content-Type",
                mime[Path(name).suffix] + "; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/login":
            self.login()
            return

        if path == "/api/logout":
            with closing(connect()) as db, db:
                db.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (self.token_hash(),)
                )

            self.send_json(200, {"loggedOut": True})
            return

        if path != "/api/courses":
            self.send_json(404, {"error": "Not found."})
            return

        if not self.require_teacher():
            return

        course = self.read_course()

        if course is not None:
            with closing(connect()) as db, db:
                cursor = db.execute(
                    """
                    INSERT INTO courses
                        (name, description, subject, credits)
                    VALUES (?, ?, ?, ?)
                    """,
                    course
                )

                self.send_json(201, {"id": cursor.lastrowid})

    def do_PUT(self):
        course_id = self.course_id()

        if course_id is None:
            self.send_json(404, {"error": "Not found."})
            return

        if not self.require_teacher():
            return

        course = self.read_course()

        if course is not None:
            with closing(connect()) as db, db:
                result = db.execute(
                    """
                    UPDATE courses
                    SET name = ?, description = ?, subject = ?, credits = ?
                    WHERE id = ?
                    """,
                    (*course, course_id)
                )

                if result.rowcount:
                    self.send_json(200, {"id": course_id})
                else:
                    self.send_json(404, {"error": "Course not found."})

    def do_DELETE(self):
        course_id = self.course_id()

        if course_id is None:
            self.send_json(404, {"error": "Not found."})
            return

        if not self.require_teacher():
            return

        with closing(connect()) as db, db:
            result = db.execute(
                "DELETE FROM courses WHERE id = ?",
                (course_id,)
            )

            if result.rowcount:
                self.send_json(200, {"deleted": True})
            else:
                self.send_json(404, {"error": "Course not found."})


if __name__ == "__main__":
    initialize()

    if len(sys.argv) == 4 and sys.argv[1] == "create-user":
        try:
            create_user(
                sys.argv[2],
                getpass.getpass("Password (12–128 characters): "),
                sys.argv[3]
            )
            print("Account created.")

        except (ValueError, sqlite3.IntegrityError) as error:
            print(error)
            sys.exit(1)

    elif len(sys.argv) == 1:
        port = int(os.environ.get("PORT", "8000"))
        print(f"Open http://localhost:{port}")
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

    else:
        print("Use: python backend.py create-user USERNAME teacher|student")
        sys.exit(1)
