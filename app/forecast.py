"""Future Prediction module: next-year budget, 1-year balance forecast, projections.
All results are estimates derived from past data (REQ-NF04, REQ-NF05). Money = minor units."""

LOW_CONFIDENCE_MONTHS = 3
SCENARIOS = {"conservative": (0.90, 1.10), "expected": (1.0, 1.0), "optimistic": (1.05, 0.95)}


def confidence(n_months):
    if n_months >= 6:
        return "good"
    return "fair" if n_months >= LOW_CONFIDENCE_MONTHS else "low"


def note(n_months):
    if n_months == 0:
        return "No completed months of history yet, so figures are based on the current month only."
    if n_months < LOW_CONFIDENCE_MONTHS:
        return f"Only {n_months} month(s) of history are available; treat these estimates with caution."
    return f"Estimates are based on {n_months} month(s) of your recorded history and are not guaranteed."


def next_year_budget(cat_totals, n_months, buffer_pct=5.0, inflation_pct=0.0):
    """cat_totals: {category: total spent across the n_months window}."""
    n = max(n_months, 1)
    rows = []
    for cat, total in sorted(cat_totals.items(), key=lambda kv: -kv[1]):
        avg = total / n
        monthly = round(avg * (1 + inflation_pct / 100) * (1 + buffer_pct / 100) / 100) * 100
        rows.append({"category": cat, "past_monthly_avg": round(avg), "suggested_monthly": monthly,
                     "suggested_yearly": monthly * 12, "past_total": total})
    return {
        "categories": rows,
        "total_monthly": sum(r["suggested_monthly"] for r in rows),
        "total_yearly": sum(r["suggested_yearly"] for r in rows),
        "past_total": sum(r["past_total"] for r in rows),
        "months_of_data": n_months, "confidence": confidence(n_months), "note": note(n_months),
        "assumptions": {"buffer_pct": buffer_pct, "inflation_pct": inflation_pct},
    }


def project(start_balance, avg_income, avg_expense, income_growth_pct=0.0, expense_growth_pct=0.0,
            months=12, start_month=None):
    """Month-by-month projection for the three scenarios; growth rates are annual %."""
    from .queries import add_months, current_month
    start_month = start_month or current_month()
    gi, ge = (1 + income_growth_pct / 100) ** (1 / 12), (1 + expense_growth_pct / 100) ** (1 / 12)
    result = {}
    for name, (im, em) in SCENARIOS.items():
        bal, rows = start_balance, []
        for i in range(1, months + 1):
            inc = round(avg_income * im * gi ** i)
            exp = round(avg_expense * em * ge ** i)
            bal += inc - exp
            rows.append({"month": add_months(start_month, i), "income": inc, "expense": exp,
                         "net": inc - exp, "balance": bal})
        result[name] = {"rows": rows, "final_balance": bal,
                        "total_income": sum(r["income"] for r in rows),
                        "total_expense": sum(r["expense"] for r in rows)}
    return result
