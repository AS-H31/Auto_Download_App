"""
Sharia Compliance Screener
AAOIFI Sharia Standard No. 21 — Section 3/4 Financial Ratio Framework
"""

import sys
import time
from datetime import date

import yfinance as yf

# ── AAOIFI threshold constants (Clause 3/4/2, 3/4/3, 3/4/4) ─────────────────
# Change these to 0.33 to align with DJIM (Dow Jones Islamic Market) standards
DEBT_THRESHOLD          = 0.30   # Clause 3/4/2: Total Debt / Market Cap < 30%
DEPOSIT_THRESHOLD       = 0.30   # Clause 3/4/3: Cash & Deposits / Market Cap < 30%
HARAM_INCOME_THRESHOLD  = 0.05   # Clause 3/4/4: Haram Income / Total Revenue < 5%


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_usd(value, width: int = 22) -> str:
    """Format a monetary value right-aligned with $ prefix and thousand separators."""
    if value is None:
        return "N/A"
    num_str = f"{value:,.0f}"
    return f"${num_str}".rjust(width)


def fmt_pct(value: float) -> str:
    """Format a ratio as a percentage string to 2 decimal places."""
    return f"{value * 100:.2f}%"


def banner():
    """Print the welcome banner."""
    print()
    print("┌──────────────────────────────────────────────────────────────────┐")
    print("│      SHARIA COMPLIANCE SCREENER                                 │")
    print("│      AAOIFI Sharia Standard No. 21 — Section 3/4               │")
    print("│      Data source: yfinance                                      │")
    print("└──────────────────────────────────────────────────────────────────┘")
    print()


def _progress(label: str):
    """Print a progress label, flush, then let the caller print 'done'."""
    print(f"  {label:<35}", end="", flush=True)


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_with_retry(fn, retries: int = 1):
    """Call fn(); on exception retry once after 3 s, then re-raise."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt < retries:
                print(f"\n  [warning] fetch failed ({exc}), retrying in 3 s…", flush=True)
                time.sleep(3)
            else:
                raise


def _ask_manual(field_name: str, numeric: bool = True):
    """Prompt the user to supply a missing value manually."""
    print(f"\n  [warning] Could not fetch '{field_name}' automatically.")
    while True:
        raw = input(f"  Enter '{field_name}' manually: ").strip()
        if not numeric:
            return raw
        try:
            return float(raw.replace(",", "").replace("$", ""))
        except ValueError:
            print("  Please enter a valid number.")


def fetch_data(ticker_symbol: str) -> dict:
    """
    Fetch all required financial data via yfinance.
    Returns a dict with all fields needed for AAOIFI Section 3/4 checks.
    """
    print()
    print(f"  Fetching data for {ticker_symbol.upper()}…")
    print()

    # ── Resolve ticker ────────────────────────────────────────────────────────
    _progress("Resolving ticker…")
    try:
        ticker = _fetch_with_retry(lambda: yf.Ticker(ticker_symbol))
        info   = _fetch_with_retry(lambda: ticker.info)
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None \
                and info.get("marketCap") is None:
            # yfinance returns an empty-ish dict for unknown tickers
            raise ValueError("ticker not recognised")
        print("done")
    except Exception as exc:
        print(f"\n  [error] Cannot resolve ticker '{ticker_symbol}': {exc}")
        sys.exit(1)

    data: dict = {
        "ticker_symbol":    ticker_symbol.upper(),
        "fetch_date":       date.today().isoformat(),
        "haram_income":     None,   # filled in later by user prompt
    }

    # ── Market Cap (Clause 3/4/2 & 3/4/3 denominator) ────────────────────────
    _progress("Fetching market cap…")
    try:
        data["market_cap"] = _fetch_with_retry(lambda: info["marketCap"])
        print("done")
    except (KeyError, Exception):
        print("missing")
        data["market_cap"] = _ask_manual("marketCap")

    # ── Balance sheet fields ──────────────────────────────────────────────────
    _progress("Fetching balance sheet…")
    try:
        bs = _fetch_with_retry(lambda: ticker.balance_sheet)
        print("done")
    except Exception as exc:
        print(f"failed ({exc})")
        bs = None

    # Total Debt — Clause 3/4/2 numerator
    try:
        data["total_debt"] = float(bs.loc["Total Debt"].iloc[0])
    except Exception:
        print("  [warning] 'Total Debt' not found in balance sheet.")
        data["total_debt"] = _ask_manual("Total Debt")

    # Cash & Deposits — Clause 3/4/3 numerator (sum of two lines, each optional)
    cash = 0.0
    cash_components = []
    for field in ("Cash And Cash Equivalents", "Other Short Term Investments"):
        try:
            val = float(bs.loc[field].iloc[0])
            cash += val
            cash_components.append(f"{field}: {fmt_usd(val)}")
        except Exception:
            pass   # silently skip missing component

    if cash == 0.0 and not cash_components:
        print("  [warning] Neither cash field found in balance sheet.")
        cash = _ask_manual("Cash & Deposits (combined)")
    data["cash_and_deposits"]    = cash
    data["cash_components"]      = cash_components

    # ── Income statement ──────────────────────────────────────────────────────
    _progress("Fetching income statement…")
    try:
        fin = _fetch_with_retry(lambda: ticker.financials)
        print("done")
        data["total_revenue"] = float(fin.loc["Total Revenue"].iloc[0])
    except Exception:
        print("missing")
        data["total_revenue"] = _ask_manual("Total Revenue")

    # ── Shares outstanding (Clause 3/4/6/4 purification formula) ─────────────
    _progress("Fetching shares outstanding…")
    try:
        data["shares_outstanding"] = info["sharesOutstanding"]
        print("done")
    except (KeyError, Exception):
        print("missing")
        data["shares_outstanding"] = _ask_manual("Shares Outstanding")

    # ── Company metadata ──────────────────────────────────────────────────────
    _progress("Fetching company info…")
    data["company_name"] = info.get("longName") or ticker_symbol.upper()
    data["sector"]       = info.get("sector",   "Unknown")
    data["industry"]     = info.get("industry", "Unknown")
    print("done")

    print()
    print("  NOTE: All monetary values are in full USD (not $000s).")
    print()

    return data


# ── Data confirmation ─────────────────────────────────────────────────────────

def _print_data_table(data: dict):
    """Display fetched values in a summary table."""
    W = 68
    print("  Fetched values:")
    print("  " + "─" * W)
    print(f"  {'Market Cap':<30} {fmt_usd(data['market_cap'])}")
    print(f"  {'Total Debt':<30} {fmt_usd(data['total_debt'])}")
    print(f"  {'Cash & Deposits':<30} {fmt_usd(data['cash_and_deposits'])}")
    print(f"  {'Total Revenue':<30} {fmt_usd(data['total_revenue'])}")
    print(f"  {'Shares Outstanding':<30} {data['shares_outstanding']:>21,.0f}")
    print(f"  {'Sector / Industry':<30} {data['sector']} / {data['industry']}")
    print("  " + "─" * W)


def confirm_data(data: dict) -> dict:
    """
    Show the user all fetched values and allow field-by-field override.
    Returns (possibly updated) data dict.
    """
    _print_data_table(data)

    answer = input("\n  Are these values correct? (y/n): ").strip().lower()
    if answer == "n":
        print()
        overridable = [
            ("market_cap",         "Market Cap",          True),
            ("total_debt",         "Total Debt",          True),
            ("cash_and_deposits",  "Cash & Deposits",     True),
            ("total_revenue",      "Total Revenue",       True),
            ("shares_outstanding", "Shares Outstanding",  True),
            ("sector",             "Sector",              False),
            ("industry",           "Industry",            False),
        ]
        for key, label, is_numeric in overridable:
            current = data[key]
            raw = input(f"  {label} [{current}] (press Enter to keep): ").strip()
            if raw:
                if is_numeric:
                    try:
                        data[key] = float(raw.replace(",", "").replace("$", ""))
                    except ValueError:
                        print(f"  Invalid number — keeping original value.")
                else:
                    data[key] = raw
        print()
        print("  Updated values:")
        _print_data_table(data)

    return data


# ── Haram income prompt ───────────────────────────────────────────────────────

def prompt_haram_income(data: dict) -> dict:
    """
    Ask user for haram/prohibited income (Clause 3/4/4 numerator).
    Defaults to 0 with a disclaimer if the user presses Enter.
    """
    print()
    raw = input(
        "  Enter haram/prohibited income amount\n"
        "  (press Enter to skip, defaults to 0): "
    ).strip()

    if not raw:
        data["haram_income"]          = 0.0
        data["haram_income_assumed"]  = True
    else:
        try:
            data["haram_income"]         = float(raw.replace(",", "").replace("$", ""))
            data["haram_income_assumed"] = False
        except ValueError:
            print("  Invalid number — defaulting to 0.")
            data["haram_income"]         = 0.0
            data["haram_income_assumed"] = True

    return data


# ── Screening logic ───────────────────────────────────────────────────────────

def run_checks(data: dict) -> dict:
    """
    Run all four AAOIFI Section 3/4 screening checks.
    Returns a results dict.  All checks run regardless of earlier failures.
    """
    results: dict = {}

    # ── Clause 3/4/1: Business Activity Screen ───────────────────────────────
    print()
    print("  ── Clause 3/4/1: Business Activity Screen ─────────────────────────")
    print(f"  Sector:   {data['sector']}")
    print(f"  Industry: {data['industry']}")
    print()
    prohibited_examples = (
        "conventional banking, insurance, alcohol, tobacco, pork,\n"
        "  gambling, adult entertainment"
    )
    answer = input(
        f"  Does the core business involve any prohibited activity?\n"
        f"  ({prohibited_examples}) [y/n]: "
    ).strip().lower()

    results["clause_3_4_1"] = {
        "label":   "Business Activity",
        "value":   "Prohibited" if answer == "y" else "Permissible",
        "ratio":   None,
        "limit":   None,
        "pass":    answer != "y",
        "detail":  None,
    }

    # ── Clause 3/4/2: Interest-Bearing Debt Ratio ────────────────────────────
    # Formula: Total Debt / Market Cap  (must be < DEBT_THRESHOLD)
    debt_ratio = data["total_debt"] / data["market_cap"]
    results["clause_3_4_2"] = {
        "label":  "Debt / Market Cap",
        "value":  fmt_pct(debt_ratio),
        "ratio":  debt_ratio,
        "limit":  DEBT_THRESHOLD,
        "pass":   debt_ratio < DEBT_THRESHOLD,
        "detail": None,
    }

    # ── Clause 3/4/3: Interest-Taking Deposits Ratio ─────────────────────────
    # Formula: Cash & Deposits / Market Cap  (must be < DEPOSIT_THRESHOLD)
    deposit_ratio = data["cash_and_deposits"] / data["market_cap"]
    results["clause_3_4_3"] = {
        "label":  "Deposits / Market Cap",
        "value":  fmt_pct(deposit_ratio),
        "ratio":  deposit_ratio,
        "limit":  DEPOSIT_THRESHOLD,
        "pass":   deposit_ratio < DEPOSIT_THRESHOLD,
        "detail": None,
    }

    # ── Clause 3/4/4: Prohibited Income Ratio ────────────────────────────────
    # Formula: Haram Income / Total Revenue  (must be < HARAM_INCOME_THRESHOLD)
    haram_ratio = data["haram_income"] / data["total_revenue"] \
        if data["total_revenue"] else 0.0
    results["clause_3_4_4"] = {
        "label":   "Haram Income %",
        "value":   fmt_pct(haram_ratio),
        "ratio":   haram_ratio,
        "limit":   HARAM_INCOME_THRESHOLD,
        "pass":    haram_ratio < HARAM_INCOME_THRESHOLD,
        "assumed": data.get("haram_income_assumed", False),
        "detail":  None,
    }

    # ── Non-compliance detail strings ─────────────────────────────────────────
    if not results["clause_3_4_2"]["pass"]:
        excess = debt_ratio - DEBT_THRESHOLD
        results["clause_3_4_2"]["detail"] = (
            f"Debt ratio {fmt_pct(debt_ratio)} exceeds "
            f"{fmt_pct(DEBT_THRESHOLD)} limit by "
            f"{excess * 100:.2f}pp"
        )

    if not results["clause_3_4_3"]["pass"]:
        excess = deposit_ratio - DEPOSIT_THRESHOLD
        results["clause_3_4_3"]["detail"] = (
            f"Deposit ratio {fmt_pct(deposit_ratio)} exceeds "
            f"{fmt_pct(DEPOSIT_THRESHOLD)} limit by "
            f"{excess * 100:.2f}pp"
        )

    if not results["clause_3_4_4"]["pass"]:
        excess = haram_ratio - HARAM_INCOME_THRESHOLD
        results["clause_3_4_4"]["detail"] = (
            f"Haram income ratio {fmt_pct(haram_ratio)} exceeds "
            f"{fmt_pct(HARAM_INCOME_THRESHOLD)} limit by "
            f"{excess * 100:.2f}pp"
        )

    if not results["clause_3_4_1"]["pass"]:
        results["clause_3_4_1"]["detail"] = (
            "Core business involves prohibited activity"
        )

    return results


# ── Results display ───────────────────────────────────────────────────────────

def display_results(ticker_symbol: str, data: dict, results: dict):
    """Print the full screening results table and overall verdict."""
    W = 68
    overall_pass = all(r["pass"] for r in results.values())

    print()
    print(f"┌{'─' * W}┐")
    company_line = f"  SHARIA COMPLIANCE SCREENING — {data['company_name']} ({ticker_symbol})"
    print(f"│{company_line:<{W}}│")
    print(f"│{'  AAOIFI Sharia Standard No. 21 — Section 3/4':<{W}}│")
    date_line = f"  Data source: yfinance  |  As of: {data['fetch_date']}"
    print(f"│{date_line:<{W}}│")
    print(f"└{'─' * W}┘")

    # ── Fetched values summary ────────────────────────────────────────────────
    print()
    print("  Fetched values:")
    print("  " + "─" * W)
    print(f"  {'Market Cap':<30} {fmt_usd(data['market_cap'])}")
    print(f"  {'Total Debt':<30} {fmt_usd(data['total_debt'])}")
    print(f"  {'Cash & Deposits':<30} {fmt_usd(data['cash_and_deposits'])}")
    print(f"  {'Total Revenue':<30} {fmt_usd(data['total_revenue'])}")
    print(f"  {'Shares Outstanding':<30} {data['shares_outstanding']:>21,.0f}")
    print(f"  {'Sector / Industry':<30} {data['sector']} / {data['industry']}")
    print("  " + "─" * W)

    # ── Screening results table ───────────────────────────────────────────────
    print()
    print("  Screening results:")
    print("  " + "─" * W)

    # Clause 3/4/1
    r1    = results["clause_3_4_1"]
    pass1 = "PASS" if r1["pass"] else "FAIL"
    print(f"  Clause 3/4/1  {r1['label']:<22} {r1['value']:<20} {pass1}")

    # Clause 3/4/2
    r2    = results["clause_3_4_2"]
    pass2 = "PASS" if r2["pass"] else "FAIL"
    limit2 = f"(limit {fmt_pct(r2['limit'])})"
    print(f"  Clause 3/4/2  {r2['label']:<22} {r2['value']:<8} {limit2:<14} {pass2}")

    # Clause 3/4/3
    r3    = results["clause_3_4_3"]
    pass3 = "PASS" if r3["pass"] else "FAIL"
    limit3 = f"(limit {fmt_pct(r3['limit'])})"
    print(f"  Clause 3/4/3  {r3['label']:<22} {r3['value']:<8} {limit3:<14} {pass3}")

    # Clause 3/4/4
    r4      = results["clause_3_4_4"]
    pass4   = "PASS" if r4["pass"] else "FAIL"
    limit4  = f"(limit {fmt_pct(r4['limit'])})"
    assumed = " *" if r4.get("assumed") else ""
    print(f"  Clause 3/4/4  {r4['label']:<22} {r4['value']:<8} {limit4:<14} {pass4}{assumed}")

    # Disclaimer for assumed haram income
    if r4.get("assumed"):
        print()
        print("  * Haram income assumed 0 — verify revenue segments manually if mixed business")

    print("  " + "─" * W)

    # ── Overall verdict ───────────────────────────────────────────────────────
    if overall_pass:
        print("  OVERALL VERDICT:  ✓ COMPLIANT")
    else:
        print("  OVERALL VERDICT:  ✗ NON-COMPLIANT")

    print("  " + "─" * W)

    # ── Non-compliance reasons ────────────────────────────────────────────────
    if not overall_pass:
        print()
        print("  Non-compliance reasons:")
        clause_keys = ["clause_3_4_1", "clause_3_4_2", "clause_3_4_3", "clause_3_4_4"]
        clause_labels = ["3/4/1", "3/4/2", "3/4/3", "3/4/4"]
        for key, label in zip(clause_keys, clause_labels):
            r = results[key]
            if not r["pass"] and r["detail"]:
                print(f"  - Clause {label}: {r['detail']}")

    print()
    return overall_pass


# ── Purification calculation (Clause 3/4/6/4) ────────────────────────────────

def calculate_purification(data: dict) -> float:
    """
    Clause 3/4/6/4: Per-share purification amount.
    Formula: (haram_income / shares_outstanding) * shares_owned
    Only called when overall verdict is COMPLIANT and haram_income > 0.
    """
    print("  ── Purification Calculation (Clause 3/4/6/4) ───────────────────────")
    while True:
        raw = input("  Enter number of shares you own: ").strip()
        try:
            shares_owned = float(raw.replace(",", ""))
            break
        except ValueError:
            print("  Please enter a valid number.")

    # Clause 3/4/6/4: purification per share × shares owned
    per_share     = data["haram_income"] / data["shares_outstanding"]
    purification  = per_share * shares_owned

    print()
    print(f"  Haram income per share  = {fmt_usd(data['haram_income'])} / "
          f"{data['shares_outstanding']:,.0f} shares = ${per_share:.6f}/share")
    print(f"  Purification amount     = ${per_share:.6f} × {shares_owned:,.0f} shares")
    print(f"                          = {fmt_usd(purification)}")
    print()
    print("  This amount should be donated to charity without seeking reward.")
    print()

    return purification


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    banner()

    ticker_symbol = input("  Enter ticker symbol (e.g. PLD, DLR, AAPL): ").strip().upper()
    if not ticker_symbol:
        print("  [error] No ticker entered. Exiting.")
        sys.exit(1)

    # Step 1: fetch
    data = fetch_data(ticker_symbol)

    # Step 2: confirm / override
    data = confirm_data(data)

    # Step 3: prompt for haram income
    data = prompt_haram_income(data)

    # Step 4: run all checks
    results = run_checks(data)

    # Step 5: display full results
    overall_pass = display_results(ticker_symbol, data, results)

    # Step 6: purification (only if compliant AND haram income > 0)
    if overall_pass and data.get("haram_income", 0) > 0:
        calculate_purification(data)


if __name__ == "__main__":
    main()
