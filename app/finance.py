"""Categories, transactions, budgets and savings goals (REQ-F05 to REQ-F14, REQ-F20 to REQ-F22)."""
import csv
import io
import math
from datetime import datetime, timezone

from flask import Blueprint, Response, g, jsonify, request

from . import notify
from .auth import body
from .db import get_db, integrity_errors
from .queries import budget_status, current_month, goal_view
from .utils import (PAYMENT_METHODS, ApiError, clean_text, login_required, parse_date, parse_int,
                    parse_month, to_major, to_minor)

bp = Blueprint("finance", __name__, url_prefix="/api")
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731


# ------------------------------------------------------------------ categories
@bp.get("/categories")
@login_required
def list_categories():
    rows = get_db().all("SELECT id, name, type FROM categories WHERE user_id=? ORDER BY type DESC, name", (g.uid,))
    return jsonify({"items": rows, "payment_methods": PAYMENT_METHODS})


@bp.post("/categories")
@login_required
def add_category():
    data, db = body(), get_db()
    name = clean_text(data.get("name"), "name", 40, required=True)
    typ = data.get("type")
    if typ not in ("income", "expense"):
        raise ApiError("type must be income or expense", 400, "type")
    try:
        cid = db.insert("INSERT INTO categories (user_id, name, type) VALUES (?,?,?)", (g.uid, name, typ))
    except integrity_errors():
        raise ApiError("This category already exists", 409, "name")
    return jsonify({"id": cid, "name": name, "type": typ}), 201


# ------------------------------------------------------------------ transactions
def _txn_row(r):
    return {"id": r["id"], "type": r["type"], "amount": to_major(r["amount"]), "date": r["date"],
            "category_id": r["category_id"], "category": r["category"], "payment_method": r["payment_method"],
            "notes": r["notes"] or "", "created_at": r["created_at"]}


TXN_SELECT = ("SELECT t.id, t.type, t.amount, t.date, t.category_id, c.name AS category, "
              "t.payment_method, t.notes, t.created_at FROM transactions t "
              "JOIN categories c ON c.id=t.category_id")


def _validate_txn(data, db):
    typ = data.get("type")
    if typ not in ("income", "expense"):
        raise ApiError("type must be income or expense", 400, "type")
    amount = to_minor(data.get("amount"))
    date = parse_date(data.get("date"))
    cat = db.one("SELECT id, type FROM categories WHERE id=? AND user_id=?", (data.get("category_id"), g.uid))
    if not cat:
        raise ApiError("Choose a valid category", 400, "category_id")
    if cat["type"] != typ:
        raise ApiError(f"Category does not match the {typ} type", 400, "category_id")
    pm = data.get("payment_method") or "Other"
    if pm not in PAYMENT_METHODS:
        raise ApiError("Invalid payment method", 400, "payment_method")
    notes = clean_text(data.get("notes"), "notes", 500)
    return typ, amount, date, cat["id"], pm, notes


def _month_effects(db, month):
    notify.evaluate_budget_alerts(db, g.uid, month)


def _filters(args):
    where, params = ["t.user_id=?"], [g.uid]
    if args.get("type") in ("income", "expense"):
        where.append("t.type=?"); params.append(args["type"])
    if args.get("category_id"):
        where.append("t.category_id=?"); params.append(parse_int(args["category_id"], "category_id", 1, 10**9))
    if args.get("payment_method"):
        where.append("t.payment_method=?"); params.append(args["payment_method"])
    if args.get("from"):
        where.append("t.date>=?"); params.append(parse_date(args["from"], "from"))
    if args.get("to"):
        where.append("t.date<=?"); params.append(parse_date(args["to"], "to"))
    if args.get("min_amount"):
        where.append("t.amount>=?"); params.append(to_minor(args["min_amount"], "min_amount", allow_zero=True))
    if args.get("max_amount"):
        where.append("t.amount<=?"); params.append(to_minor(args["max_amount"], "max_amount", allow_zero=True))
    q = (args.get("q") or "").strip().lower()[:80]
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(LOWER(COALESCE(t.notes,'')) LIKE ? ESCAPE '\\' OR LOWER(c.name) LIKE ? ESCAPE '\\')")
        params += [like, like]
    return " AND ".join(where), params


SORTS = {"date_desc": "t.date DESC, t.id DESC", "date_asc": "t.date ASC, t.id ASC",
         "amount_desc": "t.amount DESC, t.id DESC", "amount_asc": "t.amount ASC, t.id ASC"}


@bp.get("/transactions")
@login_required
def list_transactions():
    db, a = get_db(), request.args
    where, params = _filters(a)
    page = parse_int(a.get("page"), "page", 1, 100000, default=1)
    per = parse_int(a.get("per_page"), "per_page", 1, 100, default=15)
    order = SORTS.get(a.get("sort"), SORTS["date_desc"])
    base = "FROM transactions t JOIN categories c ON c.id=t.category_id WHERE " + where
    agg = db.all("SELECT t.type, COUNT(*) AS n, SUM(t.amount) AS total " + base + " GROUP BY t.type", params)
    totals = {"income": 0, "expense": 0}
    count = 0
    for r in agg:
        totals[r["type"]] = int(r["total"]); count += r["n"]
    rows = db.all(f"{TXN_SELECT} WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", params + [per, (page - 1) * per])
    return jsonify({"items": [_txn_row(r) for r in rows], "total": count, "page": page, "per_page": per,
                    "pages": max(math.ceil(count / per), 1),
                    "totals": {"income": to_major(totals["income"]), "expense": to_major(totals["expense"])}})


@bp.post("/transactions")
@login_required
def add_transaction():
    data, db = body(), get_db()
    typ, amount, date, cid, pm, notes = _validate_txn(data, db)
    client_id = clean_text(data.get("client_id"), "client_id", 64) or None
    if client_id:  # idempotency: a retried request must not create duplicates (section 3.4)
        dup = db.one(f"{TXN_SELECT} WHERE t.user_id=? AND t.client_id=?", (g.uid, client_id))
        if dup:
            return jsonify(_txn_row(dup)), 200
    try:
        tid = db.insert("INSERT INTO transactions (user_id, type, amount, date, category_id, payment_method, "
                        "notes, client_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (g.uid, typ, amount, date, cid, pm, notes, client_id, now()))
    except integrity_errors():
        raise ApiError("Duplicate request", 409)
    if typ == "expense":
        _month_effects(db, date[:7])
    return jsonify(_txn_row(db.one(f"{TXN_SELECT} WHERE t.id=?", (tid,)))), 201


@bp.put("/transactions/<int:tid>")
@login_required
def edit_transaction(tid):
    db = get_db()
    old = db.one("SELECT id, date FROM transactions WHERE id=? AND user_id=?", (tid, g.uid))
    if not old:
        raise ApiError("Transaction not found", 404)
    typ, amount, date, cid, pm, notes = _validate_txn(body(), db)
    db.run("UPDATE transactions SET type=?, amount=?, date=?, category_id=?, payment_method=?, notes=? "
           "WHERE id=? AND user_id=?", (typ, amount, date, cid, pm, notes, tid, g.uid))
    if typ == "expense":
        _month_effects(db, date[:7])
    return jsonify(_txn_row(db.one(f"{TXN_SELECT} WHERE t.id=?", (tid,))))


@bp.delete("/transactions/<int:tid>")
@login_required
def delete_transaction(tid):
    if not get_db().run("DELETE FROM transactions WHERE id=? AND user_id=?", (tid, g.uid)):
        raise ApiError("Transaction not found", 404)
    return jsonify({"ok": True})


@bp.get("/transactions/export.csv")
@login_required
def export_csv():
    where, params = _filters(request.args)
    rows = get_db().all(f"{TXN_SELECT} WHERE {where} ORDER BY t.date DESC, t.id DESC", params)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Type", "Category", "Amount", "Payment method", "Notes"])
    safe = lambda s: ("'" + s) if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # noqa: E731  CSV-injection guard
    for r in rows:
        w.writerow([r["date"], r["type"], safe(r["category"]), f"{r['amount'] / 100:.2f}",
                    r["payment_method"] or "", safe(r["notes"] or "")])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=transactions.csv"})


# ------------------------------------------------------------------ budgets
def _budget_out(b):
    return {**b, "planned": to_major(b["planned"]), "spent": to_major(b["spent"]),
            "remaining": to_major(b["remaining"])}


def _validate_budget_cat(db, category_id):
    if category_id in (None, "", 0):
        return None
    c = db.one("SELECT id FROM categories WHERE id=? AND user_id=? AND type='expense'", (category_id, g.uid))
    if not c:
        raise ApiError("Choose a valid expense category", 400, "category_id")
    return c["id"]


@bp.get("/budgets")
@login_required
def list_budgets():
    month = parse_month(request.args.get("month") or current_month())
    return jsonify({"month": month, "items": [_budget_out(b) for b in budget_status(get_db(), g.uid, month)]})


@bp.post("/budgets")
@login_required
def add_budget():
    data, db = body(), get_db()
    month = parse_month(data.get("month") or current_month())
    cid = _validate_budget_cat(db, data.get("category_id"))
    amount = to_minor(data.get("amount"))
    threshold = parse_int(data.get("threshold"), "threshold", 1, 100, default=80)
    dup = db.one("SELECT id FROM budgets WHERE user_id=? AND month=? AND "
                 + ("category_id IS NULL" if cid is None else "category_id=?"),
                 (g.uid, month) if cid is None else (g.uid, month, cid))
    if dup:
        raise ApiError("A budget for this category and month already exists. Edit it instead.", 409)
    bid = db.insert("INSERT INTO budgets (user_id, category_id, month, amount, threshold, created_at) "
                    "VALUES (?,?,?,?,?,?)", (g.uid, cid, month, amount, threshold, now()))
    notify.evaluate_budget_alerts(db, g.uid, month)
    return jsonify(_budget_out(next(b for b in budget_status(db, g.uid, month) if b["id"] == bid))), 201


@bp.put("/budgets/<int:bid>")
@login_required
def edit_budget(bid):
    data, db = body(), get_db()
    b = db.one("SELECT * FROM budgets WHERE id=? AND user_id=?", (bid, g.uid))
    if not b:
        raise ApiError("Budget not found", 404)
    amount = to_minor(data.get("amount", b["amount"] / 100))
    threshold = parse_int(data.get("threshold"), "threshold", 1, 100, default=b["threshold"])
    db.run("UPDATE budgets SET amount=?, threshold=? WHERE id=? AND user_id=?", (amount, threshold, bid, g.uid))
    notify.evaluate_budget_alerts(db, g.uid, b["month"])
    return jsonify(_budget_out(next(x for x in budget_status(db, g.uid, b["month"]) if x["id"] == bid)))


@bp.delete("/budgets/<int:bid>")
@login_required
def delete_budget(bid):
    if not get_db().run("DELETE FROM budgets WHERE id=? AND user_id=?", (bid, g.uid)):
        raise ApiError("Budget not found", 404)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ savings goals
def goal_out(row):
    v = goal_view(row)
    for k in ("target_amount", "current_amount", "remaining", "monthly_needed"):
        if v.get(k) is not None:
            v[k] = to_major(v[k])
    return v


def _goal_fields(data, cur=None):
    name = clean_text(data.get("name", cur["name"] if cur else None), "name", 80, required=True)
    target = to_minor(data.get("target_amount", cur["target_amount"] / 100 if cur else None), "target_amount")
    current = to_minor(data.get("current_amount", (cur["current_amount"] / 100) if cur else 0),
                       "current_amount", allow_zero=True)
    tdate = parse_date(data.get("target_date", cur["target_date"] if cur else None), "target_date", required=False)
    return name, target, current, tdate


def _goal_done_check(db, gid):
    row = db.one("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, g.uid))
    if row and row["current_amount"] >= row["target_amount"]:
        notify.goal_reached(db, g.uid, row)
    return row


@bp.get("/goals")
@login_required
def list_goals():
    rows = get_db().all("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (g.uid,))
    return jsonify({"items": [goal_out(r) for r in rows]})


@bp.post("/goals")
@login_required
def add_goal():
    db = get_db()
    name, target, current, tdate = _goal_fields(body())
    gid = db.insert("INSERT INTO goals (user_id, name, target_amount, current_amount, target_date, created_at) "
                    "VALUES (?,?,?,?,?,?)", (g.uid, name, target, current, tdate, now()))
    return jsonify(goal_out(_goal_done_check(db, gid))), 201


@bp.put("/goals/<int:gid>")
@login_required
def edit_goal(gid):
    db = get_db()
    cur = db.one("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, g.uid))
    if not cur:
        raise ApiError("Goal not found", 404)
    name, target, current, tdate = _goal_fields(body(), cur)
    db.run("UPDATE goals SET name=?, target_amount=?, current_amount=?, target_date=? WHERE id=? AND user_id=?",
           (name, target, current, tdate, gid, g.uid))
    return jsonify(goal_out(_goal_done_check(db, gid)))


@bp.post("/goals/<int:gid>/contribute")
@login_required
def contribute(gid):
    db = get_db()
    cur = db.one("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, g.uid))
    if not cur:
        raise ApiError("Goal not found", 404)
    data = body()
    amount = to_minor(data.get("amount"))
    new = cur["current_amount"] - amount if data.get("action") == "withdraw" else cur["current_amount"] + amount
    if new < 0:
        raise ApiError("Cannot withdraw more than the saved amount", 400, "amount")
    db.run("UPDATE goals SET current_amount=? WHERE id=? AND user_id=?", (new, gid, g.uid))
    return jsonify(goal_out(_goal_done_check(db, gid)))


@bp.delete("/goals/<int:gid>")
@login_required
def delete_goal(gid):
    if not get_db().run("DELETE FROM goals WHERE id=? AND user_id=?", (gid, g.uid)):
        raise ApiError("Goal not found", 404)
    return jsonify({"ok": True})
