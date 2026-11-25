"""Reusable calculations. All money values here are integer minor units."""
import calendar
from datetime import date

from .utils import today


def current_month():
    return today().strftime("%Y-%m")


def month_bounds(month):
    y, m = map(int, month.split("-"))
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def add_months(month, n):
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(a, b):
    """Number of months from a to b (YYYY-MM)."""
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (yb - ya) * 12 + (mb - ma)


def totals(db, uid, start, end):
    rows = db.all(
        "SELECT type, SUM(amount) AS total, COUNT(*) AS n FROM transactions "
        "WHERE user_id=? AND date>=? AND date<=? GROUP BY type", (uid, start, end))
    out = {"income": 0, "expense": 0, "count": 0}
    for r in rows:
        out[r["type"]] = int(r["total"] or 0)
        out["count"] += r["n"]
    out["net"] = out["income"] - out["expense"]
    return out


def overall_balance(db, uid):
    t = totals(db, uid, "0000-01-01", "9999-12-31")
    return t["net"]


def by_category(db, uid, type_, start, end):
    rows = db.all(
        "SELECT c.id AS category_id, c.name AS category, SUM(t.amount) AS total, COUNT(*) AS n "
        "FROM transactions t JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.type=? AND t.date>=? AND t.date<=? "
        "GROUP BY c.id, c.name ORDER BY total DESC", (uid, type_, start, end))
    grand = sum(int(r["total"]) for r in rows)
    for r in rows:
        r["total"] = int(r["total"])
        r["percent"] = round(r["total"] * 100 / grand, 1) if grand else 0.0
    return rows


def by_month(db, uid, start, end):
    rows = db.all(
        "SELECT SUBSTR(date,1,7) AS month, type, SUM(amount) AS total FROM transactions "
        "WHERE user_id=? AND date>=? AND date<=? GROUP BY SUBSTR(date,1,7), type", (uid, start, end))
    out = {}
    for r in rows:
        d = out.setdefault(r["month"], {"month": r["month"], "income": 0, "expense": 0})
        d[r["type"]] = int(r["total"])
    for d in out.values():
        d["net"] = d["income"] - d["expense"]
    return dict(sorted(out.items()))


def category_month_spend(db, uid, start, end):
    """{(month, category_name): minor} for expenses."""
    rows = db.all(
        "SELECT SUBSTR(t.date,1,7) AS month, c.name AS category, SUM(t.amount) AS total "
        "FROM transactions t JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.type='expense' AND t.date>=? AND t.date<=? "
        "GROUP BY SUBSTR(t.date,1,7), c.name", (uid, start, end))
    return {(r["month"], r["category"]): int(r["total"]) for r in rows}


def budget_status(db, uid, month):
    start, end = month_bounds(month)
    budgets = db.all(
        "SELECT b.id, b.category_id, b.amount, b.threshold, c.name AS category "
        "FROM budgets b LEFT JOIN categories c ON c.id=b.category_id "
        "WHERE b.user_id=? AND b.month=? ORDER BY c.name", (uid, month))
    spent_rows = db.all(
        "SELECT category_id, SUM(amount) AS total FROM transactions "
        "WHERE user_id=? AND type='expense' AND date>=? AND date<=? GROUP BY category_id",
        (uid, start, end))
    spent = {r["category_id"]: int(r["total"]) for r in spent_rows}
    all_spent = sum(spent.values())
    out = []
    for b in budgets:
        s = all_spent if b["category_id"] is None else spent.get(b["category_id"], 0)
        planned = int(b["amount"])
        pct = round(s * 100 / planned, 1) if planned else 0.0
        level = "over" if s > planned else ("warning" if pct >= b["threshold"] else "ok")
        out.append({
            "id": b["id"], "month": month, "category_id": b["category_id"],
            "category": b["category"] or "All spending", "planned": planned, "spent": s,
            "remaining": planned - s, "percent": pct, "threshold": b["threshold"], "level": level,
        })
    out.sort(key=lambda x: (x["category_id"] is not None, x["category"]))
    return out


def goal_view(g):
    """Add computed progress fields to a goal row (minor units)."""
    target, current = int(g["target_amount"]), int(g["current_amount"])
    remaining = max(target - current, 0)
    view = {
        "id": g["id"], "name": g["name"], "target_amount": target, "current_amount": current,
        "remaining": remaining, "percent": min(round(current * 100 / target, 1), 100.0) if target else 0.0,
        "target_date": g["target_date"], "monthly_needed": None, "status": "active",
    }
    if remaining == 0:
        view["status"] = "completed"
    elif g["target_date"]:
        t = date.fromisoformat(g["target_date"])
        n = today()
        months = (t.year - n.year) * 12 + (t.month - n.month)
        if t.day > n.day:
            months += 1
        if t < n:
            view["status"] = "overdue"
            view["monthly_needed"] = remaining
        else:
            months = max(months, 1)
            view["monthly_needed"] = -(-remaining // months)  # ceiling division
            view["months_left"] = months
    return view
