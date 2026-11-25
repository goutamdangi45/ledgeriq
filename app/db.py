"""Tiny DB layer: the same SQL runs on SQLite (local) and PostgreSQL (production)."""
import os
import sqlite3

from flask import current_app, g

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id {pk}, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR', notify_budget INTEGER NOT NULL DEFAULT 1,
        notify_goals INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS categories (
        id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL, type TEXT NOT NULL, UNIQUE (user_id, name, type))""",
    """CREATE TABLE IF NOT EXISTS transactions (
        id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type TEXT NOT NULL, amount BIGINT NOT NULL, date TEXT NOT NULL,
        category_id INTEGER NOT NULL REFERENCES categories(id),
        payment_method TEXT, notes TEXT, client_id TEXT, created_at TEXT NOT NULL,
        UNIQUE (user_id, client_id))""",
    "CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions (user_id, date)",
    """CREATE TABLE IF NOT EXISTS budgets (
        id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
        month TEXT NOT NULL, amount BIGINT NOT NULL, threshold INTEGER NOT NULL DEFAULT 80,
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS goals (
        id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL, target_amount BIGINT NOT NULL, current_amount BIGINT NOT NULL DEFAULT 0,
        target_date TEXT, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS notifications (
        id {pk}, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, message TEXT NOT NULL, dedupe_key TEXT,
        is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        UNIQUE (user_id, dedupe_key))""",
]


def integrity_errors():
    errs = [sqlite3.IntegrityError]
    try:
        import psycopg2
        errs.append(psycopg2.IntegrityError)
    except ImportError:
        pass
    return tuple(errs)


class DB:
    def __init__(self, url):
        self.pg = url.startswith(("postgres://", "postgresql://"))
        if self.pg:
            import psycopg2
            import psycopg2.extras
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            self.conn = psycopg2.connect(url)
            self._cursor_factory = psycopg2.extras.RealDictCursor
        else:
            path = url.split("sqlite:///", 1)[1]
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            self.conn = sqlite3.connect(path, timeout=15)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self._cursor_factory = None

    def _cur(self):
        return self.conn.cursor(cursor_factory=self._cursor_factory) if self.pg else self.conn.cursor()

    def _sql(self, sql):
        return sql.replace("?", "%s") if self.pg else sql

    def _exec(self, sql, args=()):
        cur = self._cur()
        try:
            cur.execute(self._sql(sql), tuple(args))
        except Exception:
            self.conn.rollback()
            raise
        return cur

    def all(self, sql, args=()):
        cur = self._exec(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        return rows

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def run(self, sql, args=(), commit=True):
        cur = self._exec(sql, args)
        count = cur.rowcount
        cur.close()
        if commit:
            self.conn.commit()
        return count

    def insert(self, sql, args=(), commit=True):
        cur = self._exec(sql + " RETURNING id", args)
        new_id = cur.fetchone()["id"]
        cur.close()
        if commit:
            self.conn.commit()
        return new_id

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

    def init_schema(self):
        pk = "SERIAL PRIMARY KEY" if self.pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        if self.pg:  # serialise start-up of several gunicorn workers
            self.run("SELECT pg_advisory_lock(727001)", commit=False)
        try:
            for stmt in SCHEMA:
                self.run(stmt.format(pk=pk), commit=False)
            self.commit()
        finally:
            if self.pg:
                self.run("SELECT pg_advisory_unlock(727001)")


def get_db():
    if "db" not in g:
        g.db = DB(current_app.config["DATABASE_URL"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        get_db().init_schema()
