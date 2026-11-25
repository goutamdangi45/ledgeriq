"""Create a demo account with ~6 months of realistic data.  Usage: python seed_demo.py
Login: demo@ledgeriq.app / Demo@1234   (for local demos only - do not run against a real production DB)"""
import random
from datetime import date, datetime, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from app.auth import DEFAULT_EXPENSE, DEFAULT_INCOME, HASH_METHOD
from app.db import get_db
from app.queries import add_months, current_month

EMAIL, PASSWORD = "demo@ledgeriq.app", "Demo@1234"


def seed():
    app = create_app()
    with app.app_context():
        db = get_db()
        if db.one("SELECT id FROM users WHERE email=?", (EMAIL,)):
            print("Demo user already exists:", EMAIL); return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        uid = db.insert("INSERT INTO users (name,email,password_hash,currency,created_at) VALUES (?,?,?,?,?)",
                        ("Demo User", EMAIL, generate_password_hash(PASSWORD, method=HASH_METHOD), "INR", now))
        cats = {}
        for n in DEFAULT_EXPENSE:
            cats[("expense", n)] = db.insert("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)", (uid, n, "expense"))
        for n in DEFAULT_INCOME:
            cats[("income", n)] = db.insert("INSERT INTO categories (user_id,name,type) VALUES (?,?,?)", (uid, n, "income"))
        rnd = random.Random(42)
        cm, today = current_month(), date.today()
        plan = [("Food", 9000, 14), ("Travel", 3500, 5), ("Shopping", 4500, 4), ("Bills", 7500, 4),
                ("Entertainment", 2500, 4), ("Education", 2000, 1), ("Health", 1500, 2)]
        methods = ["UPI", "Card", "Cash", "Net Banking"]
        for i in range(6, -1, -1):
            m = add_months(cm, -i)
            db.insert("INSERT INTO transactions (user_id,type,amount,date,category_id,payment_method,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (uid, "income", 65000 * 100, f"{m}-01", cats[("income", "Salary")], "Net Banking", "Monthly salary", now))
            if rnd.random() < .5:
                db.insert("INSERT INTO transactions (user_id,type,amount,date,category_id,payment_method,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
                          (uid, "income", rnd.randint(5, 12) * 1000 * 100, f"{m}-18", cats[("income", "Freelance")], "UPI", "Freelance project", now))
            for cat, monthly, n in plan:
                for _ in range(n):
                    day = rnd.randint(2, 28)
                    if m == cm and day > today.day:
                        continue
                    amt = int(monthly / n * rnd.uniform(.6, 1.4) * (1.35 if cat == "Food" and i < 3 else 1)) * 100
                    db.insert("INSERT INTO transactions (user_id,type,amount,date,category_id,payment_method,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
                              (uid, "expense", amt, f"{m}-{day:02d}", cats[("expense", cat)], rnd.choice(methods), f"{cat} spend", now))
        for i in range(0, 3):
            m = add_months(cm, -i)
            db.insert("INSERT INTO budgets (user_id,category_id,month,amount,threshold,created_at) VALUES (?,?,?,?,?,?)", (uid, cats[("expense", "Food")], m, 9000 * 100, 80, now))
            db.insert("INSERT INTO budgets (user_id,category_id,month,amount,threshold,created_at) VALUES (?,?,?,?,?,?)", (uid, None, m, 38000 * 100, 85, now))
        db.insert("INSERT INTO goals (user_id,name,target_amount,current_amount,target_date,created_at) VALUES (?,?,?,?,?,?)", (uid, "Emergency fund", 150000 * 100, 45000 * 100, f"{add_months(cm, 10)}-28", now))
        db.insert("INSERT INTO goals (user_id,name,target_amount,current_amount,target_date,created_at) VALUES (?,?,?,?,?,?)", (uid, "New laptop", 80000 * 100, 20000 * 100, f"{add_months(cm, 4)}-15", now))
        from app import notify
        notify.evaluate_budget_alerts(db, uid, cm)
        print(f"Demo data created. Login: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    seed()
