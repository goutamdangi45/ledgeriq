"""Run with:  python -m unittest discover -s tests -v"""
import os
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
from app import advisor, forecast
from app.queries import add_months, current_month
from app.utils import ApiError, to_minor


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE_URL": f"sqlite:///{self.tmp}/t.db", "TESTING": True})
        self.c = self.app.test_client()
        self.csrf = self.c.get("/api/auth/me").get_json()["csrf"]

    def call(self, method, url, **kw):
        h = {"X-CSRF-Token": self.csrf}
        r = getattr(self.c, method)(url, headers=h, **kw)
        return r

    def post(self, url, data=None):
        return self.call("post", url, json=data or {})

    def put(self, url, data):
        return self.call("put", url, json=data)

    def register(self, email="a@x.com", name="Alice"):
        r = self.post("/api/auth/register", {"name": name, "email": email, "password": "Passw0rd!"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.csrf = r.get_json()["csrf"]
        return r.get_json()["user"]

    def cats(self):
        items = self.c.get("/api/categories").get_json()["items"]
        return {(i["type"], i["name"]): i["id"] for i in items}

    def txn(self, typ, amount, cat, d=None, **kw):
        c = self.cats()[(typ, cat)]
        return self.post("/api/transactions", {"type": typ, "amount": amount, "category_id": c,
                                               "date": d or date.today().isoformat(), **kw})


class TestMoney(unittest.TestCase):
    def test_minor(self):
        self.assertEqual(to_minor("10.005"), 1001)
        self.assertEqual(to_minor(0.1) + to_minor(0.2), to_minor(0.3))
        for bad in (0, -5, "abc", "", None, "nan", "inf", 10 ** 12, True):
            with self.assertRaises(ApiError):
                to_minor(bad)


class TestAuth(Base):
    def test_register_login_logout(self):
        self.register()
        self.assertEqual(self.c.get("/api/auth/me").get_json()["user"]["email"], "a@x.com")
        self.post("/api/auth/logout")
        self.assertEqual(self.c.get("/api/transactions").status_code, 401)
        self.csrf = self.c.get("/api/auth/me").get_json()["csrf"]
        r = self.post("/api/auth/login", {"email": "A@X.com", "password": "Passw0rd!"})
        self.assertEqual(r.status_code, 200)

    def test_validation_and_duplicates(self):
        self.assertEqual(self.post("/api/auth/register", {"name": "x", "email": "bad", "password": "Passw0rd!"}).status_code, 400)
        self.assertEqual(self.post("/api/auth/register", {"name": "x", "email": "a@x.com", "password": "short"}).status_code, 400)
        self.assertEqual(self.post("/api/auth/register", {"name": "x", "email": "a@x.com", "password": "alllettersnodigit"}).status_code, 400)
        self.register()
        self.assertEqual(self.post("/api/auth/register", {"name": "x", "email": "a@x.com", "password": "Passw0rd!"}).status_code, 409)

    def test_wrong_password_and_throttle(self):
        self.register()
        self.post("/api/auth/logout")
        self.csrf = self.c.get("/api/auth/me").get_json()["csrf"]
        codes = [self.post("/api/auth/login", {"email": "a@x.com", "password": "nope"}).status_code for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_password_hashed_and_csrf_required(self):
        self.register()
        import sqlite3
        row = sqlite3.connect(f"{self.tmp}/t.db").execute("SELECT password_hash FROM users").fetchone()
        self.assertNotIn("Passw0rd", row[0])
        r = self.c.post("/api/transactions", json={})  # no CSRF header
        self.assertEqual(r.status_code, 403)

    def test_profile_update_and_password_change(self):
        self.register()
        r = self.put("/api/profile", {"name": "Alice B", "currency": "USD", "notify_budget": False})
        self.assertEqual(r.get_json()["currency"], "USD")
        self.assertFalse(r.get_json()["notify_budget"])
        self.assertEqual(self.put("/api/profile/password", {"current_password": "x", "new_password": "Newpass123"}).status_code, 400)
        self.assertEqual(self.put("/api/profile/password", {"current_password": "Passw0rd!", "new_password": "Newpass123"}).status_code, 200)


class TestTransactions(Base):
    def setUp(self):
        super().setUp()
        self.register()

    def test_crud_and_validation(self):
        r = self.txn("expense", "250.50", "Food", notes="Lunch")
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()["id"]
        self.assertEqual(self.txn("expense", 0, "Food").status_code, 400)
        self.assertEqual(self.txn("expense", -5, "Food").status_code, 400)
        wrong = self.post("/api/transactions", {"type": "expense", "amount": 5, "date": date.today().isoformat(),
                                                 "category_id": self.cats()[("income", "Salary")]})
        self.assertEqual(wrong.status_code, 400)  # category type mismatch
        bad_date = self.post("/api/transactions", {"type": "expense", "amount": 5, "date": "2026-13-45",
                                                   "category_id": self.cats()[("expense", "Food")]})
        self.assertEqual(bad_date.status_code, 400)
        c = self.cats()[("expense", "Travel")]
        r = self.put(f"/api/transactions/{tid}", {"type": "expense", "amount": 300, "date": date.today().isoformat(),
                                                  "category_id": c})
        self.assertEqual(r.get_json()["category"], "Travel")
        self.assertEqual(self.call("delete", f"/api/transactions/{tid}").status_code, 200)
        self.assertEqual(self.call("delete", f"/api/transactions/{tid}").status_code, 404)

    def test_idempotent_client_id(self):
        a = self.txn("expense", 10, "Food", client_id="abc")
        b = self.txn("expense", 10, "Food", client_id="abc")
        self.assertEqual((a.status_code, b.status_code), (201, 200))
        self.assertEqual(self.c.get("/api/transactions").get_json()["total"], 1)

    def test_search_filter_and_totals(self):
        self.txn("expense", 100, "Food", notes="Pizza 100% fun")
        self.txn("expense", 40, "Travel", notes="Bus")
        self.txn("income", 1000, "Salary")
        g = lambda q: self.c.get("/api/transactions?" + q).get_json()  # noqa: E731
        self.assertEqual(g("q=pizza")["total"], 1)
        self.assertEqual(g("q=%25")["total"], 1)  # literal % is escaped, not a wildcard
        self.assertEqual(g("type=expense")["total"], 2)
        self.assertEqual(g("min_amount=50&type=expense")["total"], 1)
        self.assertEqual(g("q=travel")["total"], 1)  # matches category name
        t = g("")["totals"]
        self.assertEqual((t["income"], t["expense"]), (1000.0, 140.0))
        self.assertEqual(g("per_page=2")["pages"], 2)

    def test_isolation_between_users(self):
        tid = self.txn("expense", 10, "Food").get_json()["id"]
        self.post("/api/auth/logout")
        self.csrf = self.c.get("/api/auth/me").get_json()["csrf"]
        self.register("b@x.com", "Bob")
        self.assertEqual(self.c.get("/api/transactions").get_json()["total"], 0)
        self.assertEqual(self.call("delete", f"/api/transactions/{tid}").status_code, 404)
        self.assertEqual(self.put(f"/api/transactions/{tid}", {}).status_code, 404)

    def test_csv_export_injection_guard(self):
        self.txn("expense", 10, "Food", notes="=HYPERLINK(\"x\")")
        csv_text = self.c.get("/api/transactions/export.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK", csv_text)


class TestBudgetsGoalsNotifications(Base):
    def setUp(self):
        super().setUp()
        self.register()

    def test_budget_status_and_alerts(self):
        food = self.cats()[("expense", "Food")]
        r = self.post("/api/budgets", {"category_id": food, "amount": 1000, "threshold": 80})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.post("/api/budgets", {"category_id": food, "amount": 5}).status_code, 409)
        self.txn("expense", 850, "Food")
        b = self.c.get("/api/budgets").get_json()["items"][0]
        self.assertEqual((b["planned"], b["spent"], b["remaining"], b["level"]), (1000.0, 850.0, 150.0, "warning"))
        self.txn("expense", 200, "Food")
        b = self.c.get("/api/budgets").get_json()["items"][0]
        self.assertEqual((b["remaining"], b["level"]), (-50.0, "over"))
        n = self.c.get("/api/notifications").get_json()
        self.assertEqual(len(n["items"]), 2)
        self.txn("expense", 1, "Food")  # no duplicate alerts
        self.assertEqual(len(self.c.get("/api/notifications").get_json()["items"]), 2)
        self.post("/api/notifications/read-all")
        self.assertEqual(self.c.get("/api/notifications").get_json()["unread"], 0)

    def test_notification_preference_off(self):
        self.put("/api/profile", {"notify_budget": False})
        food = self.cats()[("expense", "Food")]
        self.post("/api/budgets", {"category_id": food, "amount": 100})
        self.txn("expense", 500, "Food")
        self.assertEqual(self.c.get("/api/notifications").get_json()["items"], [])

    def test_total_budget_and_edit_delete(self):
        bid = self.post("/api/budgets", {"amount": 5000}).get_json()["id"]
        self.txn("expense", 100, "Food")
        self.txn("expense", 200, "Travel")
        self.assertEqual(self.c.get("/api/budgets").get_json()["items"][0]["spent"], 300.0)
        self.assertEqual(self.put(f"/api/budgets/{bid}", {"amount": 6000}).get_json()["planned"], 6000.0)
        self.assertEqual(self.call("delete", f"/api/budgets/{bid}").status_code, 200)

    def test_goals(self):
        target = (date.today() + timedelta(days=185)).isoformat()
        g = self.post("/api/goals", {"name": "Laptop", "target_amount": 60000, "current_amount": 0,
                                     "target_date": target}).get_json()
        self.assertGreater(g["monthly_needed"], 0)
        g2 = self.post(f"/api/goals/{g['id']}/contribute", {"amount": 15000}).get_json()
        self.assertEqual((g2["percent"], g2["remaining"]), (25.0, 45000.0))
        self.assertEqual(self.post(f"/api/goals/{g['id']}/contribute", {"amount": 99999, "action": "withdraw"}).status_code, 400)
        done = self.post(f"/api/goals/{g['id']}/contribute", {"amount": 45000}).get_json()
        self.assertEqual(done["status"], "completed")
        self.assertTrue(any(n["kind"] == "goal" for n in self.c.get("/api/notifications").get_json()["items"]))
        self.assertEqual(self.call("delete", f"/api/goals/{g['id']}").status_code, 200)


class TestInsights(Base):
    def setUp(self):
        super().setUp()
        self.register()

    def seed_history(self, months=4):
        cm = current_month()
        for i in range(1, months + 1):
            m = add_months(cm, -i)
            self.txn("income", 50000, "Salary", f"{m}-05")
            self.txn("expense", 12000, "Food", f"{m}-10")
            self.txn("expense", 6000, "Bills", f"{m}-12")
            self.txn("expense", 2000, "Travel", f"{m}-15")

    def test_dashboard_and_reports(self):
        self.txn("income", 1000, "Salary")
        self.txn("expense", 250, "Food")
        self.txn("expense", 150, "Food")
        d = self.c.get("/api/dashboard").get_json()
        self.assertEqual((d["totals"]["income"], d["totals"]["expense"], d["balance"]), (1000.0, 400.0, 600.0))
        self.assertEqual(d["expense_by_category"][0]["category"], "Food")
        self.assertEqual(len(d["trend"]), 6)
        r = self.c.get("/api/reports").get_json()
        self.assertEqual(r["savings_rate"], 60.0)
        self.assertEqual(r["largest_expense"]["amount"], 250.0)
        self.assertEqual(self.c.get("/api/reports?from=2026-05-01&to=2026-01-01").status_code, 400)
        self.assertIn("Total income", self.c.get("/api/reports/export.csv").get_data(as_text=True))

    def test_advisor_not_enough_data(self):
        a = self.c.get("/api/advisor").get_json()
        self.assertFalse(a["enough_data"])
        self.assertIn("not a replacement", a["disclaimer"])

    def test_advisor_flags_repeat_overspend(self):
        cm = current_month()
        food = self.cats()[("expense", "Food")]
        self.seed_history(3)
        for i in (1, 2, 3):
            self.post("/api/budgets", {"category_id": food, "amount": 8000, "month": add_months(cm, -i)})
        a = self.c.get("/api/advisor").get_json()
        self.assertTrue(a["enough_data"])
        ids = [s["id"] for s in a["suggestions"]]
        self.assertIn("over-Food", ids)
        self.assertTrue(all(s["source"] == "system-calculated" for s in a["suggestions"]))

    def test_forecast(self):
        self.seed_history(4)
        bal = self.c.get("/api/forecast/balance").get_json()
        # avg monthly net = 50000-20000 = 30000; balance now = 4*30000
        self.assertEqual(bal["current_balance"], 120000.0)
        self.assertEqual(bal["scenarios"]["expected"]["final_balance"], 120000.0 + 12 * 30000.0)
        self.assertEqual(bal["based_on"]["months"], 4)
        self.assertEqual(bal["label"], "estimate")
        self.assertLess(bal["scenarios"]["conservative"]["final_balance"], bal["scenarios"]["optimistic"]["final_balance"])
        p = self.c.get("/api/forecast/projections?income_growth_pct=10").get_json()
        self.assertEqual(len(p["projection"]["expected"]["rows"]), 12)
        plan = self.c.get("/api/forecast/next-year-budget?buffer_pct=0").get_json()
        food = next(c for c in plan["categories"] if c["category"] == "Food")
        self.assertEqual(food["suggested_monthly"], 12000.0)
        self.assertEqual(plan["total_yearly"], 12 * 20000.0)
        r = self.post("/api/forecast/apply-budget", {"months": 2, "buffer_pct": 0}).get_json()
        self.assertGreater(r["created"], 0)
        r2 = self.post("/api/forecast/apply-budget", {"months": 2, "buffer_pct": 0}).get_json()
        self.assertEqual((r2["created"], r2["skipped_existing"]), (0, r["created"]))
        self.assertEqual(self.c.get("/api/forecast/balance?income_growth_pct=999").status_code, 400)

    def test_forecast_with_no_data(self):
        bal = self.c.get("/api/forecast/balance").get_json()
        self.assertEqual(bal["based_on"]["confidence"], "low")
        self.assertEqual(self.c.get("/api/forecast/next-year-budget").get_json()["categories"], [])


class TestPure(unittest.TestCase):
    def test_projection_math(self):
        p = forecast.project(1000, 500, 300, months=3, start_month="2026-01")
        self.assertEqual(p["expected"]["final_balance"], 1000 + 3 * 200)
        self.assertEqual(p["expected"]["rows"][0]["month"], "2026-02")

    def test_goal_advice(self):
        res = advisor.generate(txn_count=20, months={"2026-01": {"income": 100000, "expense": 95000},
                                                     "2026-02": {"income": 100000, "expense": 95000}},
                               cat_spend={}, budgets=[], current_month="2026-02", elapsed_fraction=0.5,
                               goals=[{"name": "Car", "remaining": 10 ** 7, "monthly_needed": 10 ** 6, "status": "active"}])
        ids = [s["id"] for s in res["suggestions"]]
        self.assertIn("goal-Car", ids)
        self.assertIn("low-savings", ids)


class TestMisc(Base):
    def test_health_headers_and_static(self):
        r = self.c.get("/api/health")
        self.assertEqual(r.get_json(), {"status": "ok"})
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/api/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
