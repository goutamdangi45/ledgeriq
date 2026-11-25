"""Dashboard, reports, advisor, notifications and future prediction (REQ-F15 to REQ-F19, F23 to F29)."""
import calendar
import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, g, jsonify, request

from . import advisor, forecast
from .auth import body
from .db import get_db
from .finance import TXN_SELECT, _txn_row, goal_out, now
from .queries import (add_months, budget_status, by_category, by_month, category_month_spend, current_month,
                      goal_view, month_bounds, months_between, overall_balance, totals)
from .utils import ApiError, login_required, parse_month, parse_pct, to_major, today, parse_date

bp = Blueprint("insights", __name__, url_prefix="/api")


def _period():
    cm = current_month()
    start, end = month_bounds(cm)
    start = parse_date(request.args.get("from"), "from", required=False) or start
    end = parse_date(request.args.get("to"), "to", required=False) or end
    if start > end:
        raise ApiError("'from' date must be on or before 'to' date", 400, "from")
    return start, end


def _cat_out(rows):
    return [{**r, "total": to_major(r["total"])} for r in rows]


def _totals_out(t):
    return {k: (to_major(v) if k != "count" else v) for k, v in t.items()}


# ------------------------------------------------------------------ dashboard
@bp.get("/dashboard")
@login_required
def dashboard():
    db = get_db()
    start, end = _period()
    cm = current_month()
    t = totals(db, g.uid, start, end)
    trend_start, _ = month_bounds(add_months(cm, -5))
    trend = by_month(db, g.uid, trend_start, month_bounds(cm)[1])
    trend_rows = []
    for i in range(-5, 1):
        m = add_months(cm, i)
        d = trend.get(m, {"income": 0, "expense": 0})
        trend_rows.append({"month": m, "income": to_major(d["income"]), "expense": to_major(d["expense"])})
    recent = db.all(f"{TXN_SELECT} WHERE t.user_id=? ORDER BY t.date DESC, t.id DESC LIMIT 5", (g.uid,))
    budgets = budget_status(db, g.uid, cm)
    goals = db.all("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC LIMIT 4", (g.uid,))
    unread = db.one("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND is_read=0", (g.uid,))["n"]
    return jsonify({
        "period": {"from": start, "to": end}, "totals": _totals_out(t),
        "balance": to_major(overall_balance(db, g.uid)),
        "expense_by_category": _cat_out(by_category(db, g.uid, "expense", start, end)),
        "trend": trend_rows, "recent": [_txn_row(r) for r in recent],
        "budgets": [{**b, "planned": to_major(b["planned"]), "spent": to_major(b["spent"]),
                     "remaining": to_major(b["remaining"])} for b in budgets],
        "goals": [goal_out(r) for r in goals], "unread_notifications": unread,
    })


# ------------------------------------------------------------------ reports
@bp.get("/reports")
@login_required
def report():
    db = get_db()
    start, end = _period()
    t = totals(db, g.uid, start, end)
    pm = db.all("SELECT COALESCE(payment_method,'Other') AS method, SUM(amount) AS total, COUNT(*) AS n "
                "FROM transactions WHERE user_id=? AND type='expense' AND date>=? AND date<=? "
                "GROUP BY COALESCE(payment_method,'Other') ORDER BY total DESC", (g.uid, start, end))
    biggest = db.one(f"{TXN_SELECT} WHERE t.user_id=? AND t.type='expense' AND t.date>=? AND t.date<=? "
                     "ORDER BY t.amount DESC LIMIT 1", (g.uid, start, end))
    days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
    months = [{"month": m, "income": to_major(d["income"]), "expense": to_major(d["expense"]),
               "net": to_major(d["net"])} for m, d in by_month(db, g.uid, start, end).items()]
    return jsonify({
        "period": {"from": start, "to": end, "days": days}, "totals": _totals_out(t),
        "savings_rate": round(t["net"] * 100 / t["income"], 1) if t["income"] else None,
        "avg_daily_expense": to_major(round(t["expense"] / days)),
        "expense_by_category": _cat_out(by_category(db, g.uid, "expense", start, end)),
        "income_by_category": _cat_out(by_category(db, g.uid, "income", start, end)),
        "by_month": months,
        "by_payment_method": [{"method": r["method"], "total": to_major(int(r["total"])), "count": r["n"]} for r in pm],
        "largest_expense": _txn_row(biggest) if biggest else None,
    })


# ------------------------------------------------------------------ advisor
@bp.get("/advisor")
@login_required
def get_advisor():
    db = get_db()
    cm, n = current_month(), today()
    first = add_months(cm, -2)
    start, end = month_bounds(first)[0], month_bounds(cm)[1]
    user = db.one("SELECT currency FROM users WHERE id=?", (g.uid,))
    count = db.one("SELECT COUNT(*) AS n FROM transactions WHERE user_id=? AND date>=? AND date<=?",
                   (g.uid, start, end))["n"]
    months = by_month(db, g.uid, start, end)
    budgets = db.all("SELECT b.month, b.amount AS planned, c.name AS category FROM budgets b "
                     "LEFT JOIN categories c ON c.id=b.category_id WHERE b.user_id=? AND b.month>=? AND b.month<=?",
                     (g.uid, first, cm))
    goals = [goal_view(r) for r in db.all("SELECT * FROM goals WHERE user_id=?", (g.uid,))]
    result = advisor.generate(
        txn_count=count, months=months, cat_spend=category_month_spend(db, g.uid, start, end),
        budgets=[{**b, "planned": int(b["planned"])} for b in budgets], goals=goals, current_month=cm,
        elapsed_fraction=n.day / calendar.monthrange(n.year, n.month)[1], currency=user["currency"])
    return jsonify(result)


# ------------------------------------------------------------------ notifications
@bp.get("/notifications")
@login_required
def list_notifications():
    db = get_db()
    rows = db.all("SELECT id, kind, message, is_read, created_at FROM notifications WHERE user_id=? "
                  "ORDER BY id DESC LIMIT 100", (g.uid,))
    for r in rows:
        r["is_read"] = bool(r["is_read"])
    return jsonify({"items": rows, "unread": sum(1 for r in rows if not r["is_read"])})


@bp.post("/notifications/read-all")
@login_required
def read_all():
    get_db().run("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.uid,))
    return jsonify({"ok": True})


@bp.post("/notifications/<int:nid>/read")
@login_required
def read_one(nid):
    if not get_db().run("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, g.uid)):
        raise ApiError("Notification not found", 404)
    return jsonify({"ok": True})


@bp.delete("/notifications/<int:nid>")
@login_required
def delete_notification(nid):
    if not get_db().run("DELETE FROM notifications WHERE id=? AND user_id=?", (nid, g.uid)):
        raise ApiError("Notification not found", 404)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ future prediction
def _history(db):
    """Past-year baseline: completed months only (falls back to the current month if none)."""
    cm = current_month()
    last_done = add_months(cm, -1)
    win_start = month_bounds(add_months(cm, -12))[0]
    win_end = month_bounds(last_done)[1]
    first = db.one("SELECT MIN(date) AS d FROM transactions WHERE user_id=? AND date>=? AND date<=?",
                   (g.uid, win_start, win_end))["d"]
    if first:
        n = months_between(first[:7], last_done) + 1
        start = month_bounds(first[:7])[0]
        return start, win_end, n, n
    start, end = month_bounds(cm)
    return start, end, 0, 1


def _baseline():
    db = get_db()
    start, end, n_months, divisor = _history(db)
    t = totals(db, g.uid, start, end)
    cats = {r["category"]: r["total"] for r in by_category(db, g.uid, "expense", start, end)}
    return db, start, end, n_months, divisor, t, cats


def _major_rows(rows):
    return [{k: (to_major(v) if k != "month" else v) for k, v in r.items()} for r in rows]


def _projection():
    db, start, end, n_months, divisor, t, _ = _baseline()
    ig = parse_pct(request.args.get("income_growth_pct"), "income_growth_pct")
    eg = parse_pct(request.args.get("expense_growth_pct"), "expense_growth_pct")
    avg_i, avg_e = t["income"] / divisor, t["expense"] / divisor
    start_bal = overall_balance(db, g.uid)
    proj = forecast.project(start_bal, avg_i, avg_e, ig, eg)
    return {"based_on": {"from": start, "to": end, "months": n_months, "confidence": forecast.confidence(n_months),
                         "note": forecast.note(n_months)},
            "assumptions": {"income_growth_pct": ig, "expense_growth_pct": eg},
            "current_balance": to_major(start_bal), "avg_monthly_income": to_major(round(avg_i)),
            "avg_monthly_expense": to_major(round(avg_e)), "projection": proj, "label": "estimate"}


@bp.get("/forecast/balance")
@login_required
def forecast_balance():
    p = _projection()
    p["scenarios"] = {k: {"final_balance": to_major(v["final_balance"]), "total_income": to_major(v["total_income"]),
                          "total_expense": to_major(v["total_expense"])} for k, v in p.pop("projection").items()}
    return jsonify(p)


@bp.get("/forecast/projections")
@login_required
def forecast_projections():
    p = _projection()
    p["projection"] = {k: {"final_balance": to_major(v["final_balance"]), "rows": _major_rows(v["rows"])}
                       for k, v in p["projection"].items()}
    return jsonify(p)


def _budget_plan():
    buf = parse_pct(request.args.get("buffer_pct", (request.get_json(silent=True) or {}).get("buffer_pct")),
                    "buffer_pct", 0, 50, default=5.0)
    infl = parse_pct(request.args.get("inflation_pct", (request.get_json(silent=True) or {}).get("inflation_pct")),
                     "inflation_pct", 0, 50, default=0.0)
    _, start, end, n_months, divisor, _, cats = _baseline()
    return forecast.next_year_budget(cats, divisor if n_months == 0 else n_months, buf, infl) | {
        "months_of_data": n_months, "based_on": {"from": start, "to": end}}


@bp.get("/forecast/next-year-budget")
@login_required
def next_year_budget():
    plan = _budget_plan()
    for r in plan["categories"]:
        for k in ("past_monthly_avg", "suggested_monthly", "suggested_yearly", "past_total"):
            r[k] = to_major(r[k])
    for k in ("total_monthly", "total_yearly", "past_total"):
        plan[k] = to_major(plan[k])
    plan["label"] = "estimate"
    return jsonify(plan)


@bp.post("/forecast/apply-budget")
@login_required
def apply_budget():
    """Turn the suggested next-year budget into real monthly budgets (never overwrites existing ones)."""
    data, db = body(), get_db()
    month = parse_month(data.get("month") or add_months(current_month(), 1))
    count = max(1, min(int(data.get("months") or 1), 12))
    plan = _budget_plan()
    cats = {r["name"]: r["id"] for r in db.all("SELECT id, name FROM categories WHERE user_id=? AND type='expense'", (g.uid,))}
    created = skipped = 0
    for i in range(count):
        m = add_months(month, i)
        items = [(None, plan["total_monthly"])] + [(cats.get(r["category"]), r["suggested_monthly"]) for r in plan["categories"]]
        for cid, amt in items:
            if amt <= 0 or (cid is None and not plan["categories"]):
                continue
            q = "category_id IS NULL" if cid is None else "category_id=?"
            exists = db.one(f"SELECT id FROM budgets WHERE user_id=? AND month=? AND {q}",
                            (g.uid, m) if cid is None else (g.uid, m, cid))
            if exists:
                skipped += 1
                continue
            db.run("INSERT INTO budgets (user_id, category_id, month, amount, threshold, created_at) VALUES (?,?,?,?,?,?)",
                   (g.uid, cid, m, amt, 80, now()), commit=False)
            created += 1
    db.commit()
    return jsonify({"created": created, "skipped_existing": skipped, "from_month": month, "months": count})


# ------------------------------------------------------------------ report CSV
@bp.get("/reports/export.csv")
@login_required
def report_csv():
    start, end = _period()
    db = get_db()
    t = totals(db, g.uid, start, end)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Report", f"{start} to {end}"])
    w.writerow(["Total income", f"{t['income'] / 100:.2f}"])
    w.writerow(["Total expenses", f"{t['expense'] / 100:.2f}"])
    w.writerow(["Net", f"{t['net'] / 100:.2f}"])
    w.writerow([])
    w.writerow(["Expense category", "Amount", "Percent"])
    for r in by_category(db, g.uid, "expense", start, end):
        name = ("'" + r["category"]) if r["category"][:1] in "=+-@" else r["category"]
        w.writerow([name, f"{r['total'] / 100:.2f}", f"{r['percent']}"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=report.csv"})
