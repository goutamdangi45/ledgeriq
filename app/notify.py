"""Budget / goal alerts (REQ-F13, REQ-F28, REQ-F29). Alerts are de-duplicated per budget+level."""
from datetime import datetime, timezone

from .db import integrity_errors
from .queries import budget_status
from .utils import fmt_money


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add(db, uid, kind, message, key):
    if db.one("SELECT id FROM notifications WHERE user_id=? AND dedupe_key=?", (uid, key)):
        return
    try:
        db.insert("INSERT INTO notifications (user_id, kind, message, dedupe_key, created_at) "
                  "VALUES (?,?,?,?,?)", (uid, kind, message, key, _now()))
    except integrity_errors():
        pass


def evaluate_budget_alerts(db, uid, month):
    user = db.one("SELECT currency, notify_budget FROM users WHERE id=?", (uid,))
    if not user or not user["notify_budget"]:
        return
    cur = user["currency"]
    for b in budget_status(db, uid, month):
        if b["level"] == "ok":
            continue
        if b["level"] == "over":
            msg = (f"{b['category']} budget for {month} is exceeded: spent {fmt_money(b['spent'], cur)} "
                   f"of {fmt_money(b['planned'], cur)}.")
        else:
            msg = (f"{b['category']} spending has reached {b['percent']:.0f}% of the {month} budget "
                   f"({fmt_money(b['spent'], cur)} of {fmt_money(b['planned'], cur)}).")
        _add(db, uid, "budget_" + b["level"], msg, f"budget:{b['id']}:{b['level']}")


def goal_reached(db, uid, goal):
    user = db.one("SELECT notify_goals FROM users WHERE id=?", (uid,))
    if user and user["notify_goals"]:
        _add(db, uid, "goal", f"Congratulations! You reached your savings goal “{goal['name']}”.",
             f"goal:{goal['id']}:done")
