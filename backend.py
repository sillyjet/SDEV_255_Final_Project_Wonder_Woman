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
        or not 12 <= len(password) import json
import sqlite3
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / "courses.db"


def connect():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


with connect() as db:
    db.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            subject TEXT NOT NULL,
            credits INTEGER NOT NULL
        )
    """)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)


    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


    def course_id(self):
        parts = urlparse(self.path).path.split("/")
        if len(parts) == 4 and parts[:3] == ["", "api", "courses"]:
            try:
                return int(parts[3])
            except ValueError:
                pass
        return None

    def read_course(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 10000:
                raise ValueError()

            data = json.loads(self.rfile.read(length))
            name = data["name"].strip()
            description = data["description"].strip()
            subject = data["subject"].strip()
            credits = int(data["credits"])

            if not name or not description or not subject or not 1 <= credits <= 20:
                raise ValueError()

            return (name, description, subject, credits)
        except (ValueError, KeyError, TypeError, AttributeError):
            self.send_json(400, {"error": "Fill in every field. Credits must be 1–20."})
            return None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/courses":
            with connect() as db:
                rows = db.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
                self.send_json(200, [dict(row) for row in rows])
            return

        course_id = self.course_id()
        if course_id is not None:
            with connect() as db:
                row = db.execute(
                    "SELECT * FROM courses WHERE id = ?", (course_id,)
                ).fetchone()
                self.send_json(200, dict(row)) if row else self.send_json(
                    404, {"error": "Course not found."}
                )
            return

        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/courses":
            self.send_json(404, {"error": "Not found."})
            return

        course = self.read_course()
        if course is None:
            return

        with connect() as db:
            cursor = db.execute(
                "INSERT INTO courses (name, description, subject, credits) "
                "VALUES (?, ?, ?, ?)", course
            )
            self.send_json(201, {"id": cursor.lastrowid})

    def do_PUT(self):
        course_id = self.course_id()
        if course_id is None:
            self.send_json(404, {"error": "Not found."})
            return

        course = self.read_course()
        if course is None:
            return

        with connect() as db:
            result = db.execute(
                "UPDATE courses SET name = ?, description = ?, subject = ?, "
                "credits = ? WHERE id = ?",
                (*course, course_id)
            )
            self.send_json(200, {"id": course_id}) if result.rowcount else self.send_json(
                404, {"error": "Course not found."}
            )

    def do_DELETE(self):
        course_id = self.course_id()
        if course_id is None:
            self.send_json(404, {"error": "Not found."})
            return

        with connect() as db:
            result = db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            self.send_json(200, {"deleted": True}) if result.rowcount else self.send_json(
                404, {"error": "Course not found."}
            )


import os
port = int(os.environ.get("PORT", 8000))
print(f"Open http://localhost:{port}")
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

