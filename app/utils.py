"""Shared helpers: errors, validation, money handling, auth decorator."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps

from flask import g, session

MAX_MINOR = 10 ** 11  # 1,000,000,000.00 in minor units (REQ-F08 sanity limit)
CURRENCIES = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AED": "AED "}
PAYMENT_METHODS = ["Cash", "UPI", "Card", "Net Banking", "Wallet", "Other"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ApiError(Exception):
    def __init__(self, message, status=400, field=None):
        super().__init__(message)
        self.message, self.status, self.field = message, status, field


# ---------- money: stored as integer minor units (paise/cents) to avoid float drift ----------
def to_minor(value, field="amount", allow_zero=False):
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        raise ApiError(f"{field} is required", 400, field)
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError(f"{field} must be a valid number", 400, field)
    if not d.is_finite():
        raise ApiError(f"{field} must be a valid number", 400, field)
    minor = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if minor < 0 or (minor == 0 and not allow_zero):
        raise ApiError(f"{field} must be greater than zero", 400, field)
    if minor > MAX_MINOR:
        raise ApiError(f"{field} is too large", 400, field)
    return minor


def to_major(minor):
    return round((minor or 0) / 100, 2)


def fmt_money(minor, currency="INR"):
    return f"{CURRENCIES.get(currency, '')}{(minor or 0) / 100:,.2f}"


# ---------- text / date validation ----------
def clean_text(value, field, max_len, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ApiError(f"{field} must be text", 400, field)
    value = _CTRL.sub("", value).strip()
    if required and not value:
        raise ApiError(f"{field} is required", 400, field)
    if len(value) > max_len:
        raise ApiError(f"{field} must be at most {max_len} characters", 400, field)
    return value


def parse_date(value, field="date", required=True):
    if value in (None, ""):
        if required:
            raise ApiError(f"{field} is required", 400, field)
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ApiError(f"{field} must be a valid date (YYYY-MM-DD)", 400, field)


def parse_month(value, field="month"):
    try:
        return datetime.strptime(str(value), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise ApiError(f"{field} must be in YYYY-MM format", 400, field)


def parse_int(value, field, lo, hi, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise ApiError(f"{field} is required", 400, field)
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a whole number", 400, field)
    if not lo <= n <= hi:
        raise ApiError(f"{field} must be between {lo} and {hi}", 400, field)
    return n


def parse_pct(value, field, lo=-50.0, hi=100.0, default=0.0):
    if value in (None, ""):
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number", 400, field)
    if not lo <= n <= hi:
        raise ApiError(f"{field} must be between {lo:g} and {hi:g}", 400, field)
    return n


def today():
    return date.today()


# ---------- auth ----------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            raise ApiError("Please log in to continue", 401)
        g.uid = uid
        return fn(*args, **kwargs)
    return wrapper
