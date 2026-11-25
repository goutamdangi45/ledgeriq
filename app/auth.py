"""Account, session and profile endpoints (REQ-F01 to REQ-F04, REQ-NF07/08/11)."""
import secrets
import time
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, integrity_errors
from .utils import CURRENCIES, EMAIL_RE, ApiError, clean_text, login_required

bp = Blueprint("auth", __name__, url_prefix="/api")

HASH_METHOD = "pbkdf2:sha256:260000"
_DUMMY_HASH = generate_password_hash("dummy-password", method=HASH_METHOD)
_attempts = {}  # (ip, email) -> (count, first_ts) : simple brute-force throttle
MAX_ATTEMPTS, WINDOW = 5, 300

DEFAULT_EXPENSE = ["Food", "Travel", "Shopping", "Bills", "Education", "Entertainment", "Health", "Other"]
DEFAULT_INCOME = ["Salary", "Freelance", "Gift", "Investment", "Other Income"]


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be JSON", 400)
    return data


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "currency": u["currency"],
            "notify_budget": bool(u["notify_budget"]), "notify_goals": bool(u["notify_goals"])}


def _new_session(uid):
    session.clear()
    session.permanent = True
    session["uid"] = uid
    session["csrf"] = secrets.token_urlsafe(24)


def validate_password(pw):
    if not isinstance(pw, str) or len(pw) < 8 or len(pw) > 128:
        raise ApiError("Password must be 8-128 characters", 400, "password")
    if not any(c.isalpha() for c in pw) or not any(c.isdigit() for c in pw):
        raise ApiError("Password must contain at least one letter and one number", 400, "password")


@bp.get("/auth/me")
def me():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    user = None
    if session.get("uid"):
        row = get_db().one("SELECT * FROM users WHERE id=?", (session["uid"],))
        if row:
            user = public_user(row)
        else:
            session.clear()
            session["csrf"] = secrets.token_urlsafe(24)
    return jsonify({"user": user, "csrf": session["csrf"], "currencies": list(CURRENCIES)})


@bp.post("/auth/register")
def register():
    data = body()
    name = clean_text(data.get("name"), "name", 80, required=True)
    email = clean_text(data.get("email"), "email", 120, required=True).lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address", 400, "email")
    validate_password(data.get("password"))
    currency = data.get("currency") or "INR"
    if currency not in CURRENCIES:
        raise ApiError("Unsupported currency", 400, "currency")
    db = get_db()
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        raise ApiError("An account with this email already exists", 409, "email")
    try:
        uid = db.insert(
            "INSERT INTO users (name, email, password_hash, currency, created_at) VALUES (?,?,?,?,?)",
            (name, email, generate_password_hash(data["password"], method=HASH_METHOD), currency,
             datetime.now(timezone.utc).isoformat(timespec="seconds")), commit=False)
        for n in DEFAULT_EXPENSE:
            db.run("INSERT INTO categories (user_id, name, type) VALUES (?,?,?)", (uid, n, "expense"), commit=False)
        for n in DEFAULT_INCOME:
            db.run("INSERT INTO categories (user_id, name, type) VALUES (?,?,?)", (uid, n, "income"), commit=False)
        db.commit()
    except integrity_errors():
        db.rollback()
        raise ApiError("An account with this email already exists", 409, "email")
    _new_session(uid)
    return jsonify({"user": public_user(db.one("SELECT * FROM users WHERE id=?", (uid,))),
                    "csrf": session["csrf"]}), 201


@bp.post("/auth/login")
def login():
    data = body()
    email = str(data.get("email") or "").strip().lower()
    key = (request.remote_addr, email)
    count, first = _attempts.get(key, (0, time.time()))
    if time.time() - first > WINDOW:
        count, first = 0, time.time()
    if count >= MAX_ATTEMPTS:
        raise ApiError("Too many failed attempts. Please try again in a few minutes.", 429)
    row = get_db().one("SELECT * FROM users WHERE email=?", (email,))
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, str(data.get("password") or ""))
    if not (row and ok):
        _attempts[key] = (count + 1, first)
        raise ApiError("Incorrect email or password", 401)
    _attempts.pop(key, None)
    _new_session(row["id"])
    return jsonify({"user": public_user(row), "csrf": session["csrf"]})


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/profile")
@login_required
def get_profile():
    return jsonify(public_user(get_db().one("SELECT * FROM users WHERE id=?", (g.uid,))))


@bp.put("/profile")
@login_required
def update_profile():
    data, db = body(), get_db()
    cur = db.one("SELECT * FROM users WHERE id=?", (g.uid,))
    name = clean_text(data.get("name", cur["name"]), "name", 80, required=True)
    currency = data.get("currency", cur["currency"])
    if currency not in CURRENCIES:
        raise ApiError("Unsupported currency", 400, "currency")
    nb = int(bool(data.get("notify_budget", cur["notify_budget"])))
    ng = int(bool(data.get("notify_goals", cur["notify_goals"])))
    db.run("UPDATE users SET name=?, currency=?, notify_budget=?, notify_goals=? WHERE id=?",
           (name, currency, nb, ng, g.uid))
    return jsonify(public_user(db.one("SELECT * FROM users WHERE id=?", (g.uid,))))


@bp.put("/profile/password")
@login_required
def change_password():
    data, db = body(), get_db()
    row = db.one("SELECT * FROM users WHERE id=?", (g.uid,))
    if not check_password_hash(row["password_hash"], str(data.get("current_password") or "")):
        raise ApiError("Current password is incorrect", 400, "current_password")
    validate_password(data.get("new_password"))
    db.run("UPDATE users SET password_hash=? WHERE id=?",
           (generate_password_hash(data["new_password"], method=HASH_METHOD), g.uid))
    return jsonify({"ok": True})
