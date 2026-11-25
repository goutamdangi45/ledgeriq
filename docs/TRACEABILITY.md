# Requirements traceability (SRS v1.0 → implementation → tests)

| Req | Implementation | Test (tests/test_app.py) |
|---|---|---|
| F01 register | `auth.register` | `TestAuth.test_register_login_logout`, `test_validation_and_duplicates` |
| F02 authenticate before private data | `utils.login_required`, session cookie | `test_register_login_logout` |
| F03 update profile | `auth.update_profile`, `change_password` | `test_profile_update_and_password_change` |
| F04 logout | `auth.logout` | `test_register_login_logout` |
| F05 add income/expense | `finance.add_transaction` | `TestTransactions.test_crud_and_validation` |
| F06 required fields | `finance._validate_txn` | `test_crud_and_validation` |
| F07 edit/delete own | `edit_transaction`, `delete_transaction` | `test_crud_and_validation`, `test_isolation_between_users` |
| F08 reject invalid amounts | `utils.to_minor` | `TestMoney.test_minor`, `test_crud_and_validation` |
| F09 search/filter | `finance._filters` | `test_search_filter_and_totals` |
| F10 totals update | totals computed on read (`queries.totals`) | `test_search_filter_and_totals`, `test_dashboard_and_reports` |
| F11-F14 budgets | `finance` budgets routes, `queries.budget_status`, `notify` | `test_budget_status_and_alerts`, `test_total_budget_and_edit_delete` |
| F15-F19 dashboard/reports | `insights.dashboard`, `insights.report`, SVG charts | `test_dashboard_and_reports` |
| F20-F22 savings goals | `finance` goals routes, `queries.goal_view` | `test_goals` |
| F23-F27 advisor | `advisor.generate` | `test_advisor_flags_repeat_overspend`, `test_advisor_not_enough_data`, `test_goal_advice` |
| F28-F29 notifications | `notify`, `insights` notifications routes, profile prefs | `test_budget_status_and_alerts`, `test_notification_preference_off` |
| Use case: Future Prediction (next-year budget, 1-year balance, projections) | `forecast.py`, `insights` /api/forecast/* | `test_forecast`, `test_forecast_with_no_data`, `test_projection_math` |
| NF01-NF03 performance | indexed queries; aggregation in SQL | manual (dashboard < 1s on demo data) |
| NF04/NF05 calculated vs entered; no guarantees | "auto-calculated"/"estimate" tags, disclaimers | `test_advisor_flags_repeat_overspend` (source tag), UI |
| NF06 calculation correctness | integer minor units, `Decimal` parsing | `TestMoney`, `TestInsights`, `TestPure` |
| NF07 per-user isolation | every query filters `user_id` | `test_isolation_between_users` |
| NF08 hashed passwords | PBKDF2-SHA256 (260k iterations) | `test_password_hashed_and_csrf_required` |
| NF09 validation/sanitisation | `utils.clean_text`, parameterised SQL, output escaping, CSP, CSV-injection guard | `test_csv_export_injection_guard`, validation tests |
| NF10 HTTPS in production | `Secure` cookie + HSTS when `APP_ENV=production`; hosts terminate TLS | config |
| NF11 secure logout/session | HttpOnly+SameSite cookies, CSRF token, session rotated on login | `test_password_hashed_and_csrf_required` |
| §3.4 no duplicate transactions on retry | `client_id` idempotency | `test_idempotent_client_id` |
