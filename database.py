import sqlite3
import os

DATABASE = os.environ.get("DATABASE_PATH", "interviewmate.db")


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            difficulty TEXT NOT NULL DEFAULT 'Beginner',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            score INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    interview_columns = {
        row["name"] for row in connection.execute(
            "PRAGMA table_info(interviews)"
        ).fetchall()
    }
    if "difficulty" not in interview_columns:
        connection.execute(
            "ALTER TABLE interviews ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'Beginner'"
        )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    connection.close()