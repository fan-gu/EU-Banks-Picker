"""User-facing Streamlit dashboard for all 23 EURO STOXX Banks constituents."""

from pathlib import Path
from datetime import date, datetime
import json
import subprocess
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_DIR = Path(__file__).resolve().parent


@st.cache_data
def load_data():
    with (BASE_DIR / "full_universe_dataset.json").open(encoding="utf-8") as handle:
        banks = {row["ticker"]: row for row in json.load(handle)}
    with (BASE_DIR / "full_universe_scores.json").open(encoding="utf-8") as handle:
        scores = json.load(handle)
    with (BASE_DIR / "bank_master.json").open(encoding="utf-8") as handle:
        universe = json.load(handle)["constituents"]
    with (BASE_DIR / "official_report_pages.json").open(encoding="utf-8") as handle:
        report_pages = json.load(handle)
    return banks, scores, universe, report_pages


def percent(value):
    return f"{value:.1%}" if isinstance(value, (int, float)) else "Not available"


def multiple(value):
    return f"{value:.2f}x" if isinstance(value, (int, float)) else "Not available"


def short_comment(score):
    if score is None:
        return "Insufficient comparable data"
    if score >= 67:
        return "Strong relative screen; verify report risks"
    if score >= 45:
        return "Mixed signals; broadly mid-pack"
    return "Weak relative screen; review valuation and returns"


st.set_page_config(page_title="EU Banks Picker", page_icon="🏦", layout="wide")
st.title("EU Banks Picker")
st.caption("EuroSTOXX Bank Valuation Agent · relative-value research screening")

if st.button("Refresh data"):
    with st.status("Refreshing all 23 banks...", expanded=False) as status:
        result = subprocess.run([sys.executable, str(BASE_DIR / "build_full_universe.py")], cwd=BASE_DIR, capture_output=True, text=True)
        if result.returncode == 0:
            status.update(label="Refresh complete", state="complete")
            st.cache_data.clear()
            st.rerun()
        status.update(label="Refresh failed", state="error")
        st.code(result.stderr or result.stdout)

banks, scores, universe, report_pages = load_data()
ranking_tab, details_tab, coverage_tab, evidence_tab, methodology_tab = st.tabs(["Relative ranking", "Bank details", "Universe coverage", "Evidence", "Methodology"])

with ranking_tab:
    st.subheader("Relative ranking")
    timestamps = [bank.get("retrieved_at") for bank in banks.values() if bank.get("retrieved_at")]
    if timestamps:
        latest = max(timestamps)
        observed = datetime.fromisoformat(latest.replace("Z", "+00:00")).date()
        age = (date.today() - observed).days
        (st.error if age > 3 else st.info)(f"Provider data retrieved: {observed} ({age} day(s) old)." + (" Refresh before analysis." if age > 3 else ""))
    st.dataframe([
        {
            "Rank": i,
            "Bank": row["bank_name"],
            "Country": banks[row["ticker"]]["country"],
            "Current price": banks[row["ticker"]].get("metrics", {}).get("price"),
            "Screening score": row["score"],
            "Comment": short_comment(row["score"]),
        }
        for i, row in enumerate((item for item in scores if item["status"] == "ranked"), 1)
    ], use_container_width=True, hide_index=True)
    st.warning("A higher score indicates stronger relative inputs under this methodology; it is not a buy or sell recommendation.")

with details_tab:
    selected = st.selectbox("Select a bank", [row["ticker"] for row in universe])
    bank = banks[selected]
    score = next((row for row in scores if row["ticker"] == selected), {"score": None, "components": {}})
    st.subheader(f"{bank['bank_name']} ({selected})")
    st.write(f"Country: **{bank['country']}** · market ticker: **{bank['market_ticker']}**")
    metrics = bank.get("metrics", {})
    prudential = bank.get("prudential_metrics", {})
    cols = st.columns(6)
    cols[0].metric("Screening score", score["score"] if score["score"] is not None else "N/A")
    cols[1].metric("Share price", f"{metrics.get('price'):.2f}" if metrics.get("price") else "N/A")
    cols[2].metric("P/B", multiple(metrics.get("price_to_book")))
    cols[3].metric("P/E", multiple(metrics.get("price_to_earnings")))
    cols[4].metric("ROE", percent(metrics.get("return_on_equity")))
    cols[5].metric("Dividend yield", percent(metrics.get("dividend_yield")))
    st.markdown("#### Additional equity-research metrics")
    st.dataframe([
        {"Metric": "Forward P/E", "Value": multiple(metrics.get("forward_price_to_earnings"))},
        {"Metric": "Book value per share", "Value": metrics.get("book_value_per_share")},
        {"Metric": "Earnings per share", "Value": metrics.get("earnings_per_share")},
        {"Metric": "Return on assets", "Value": percent(metrics.get("return_on_assets"))},
        {"Metric": "Profit margin", "Value": percent(metrics.get("profit_margin"))},
        {"Metric": "Payout ratio", "Value": percent(metrics.get("payout_ratio"))},
        {"Metric": "Earnings growth", "Value": percent(metrics.get("earnings_growth"))},
        {"Metric": "Revenue growth", "Value": percent(metrics.get("revenue_growth"))},
        {"Metric": "Market capitalization", "Value": f"{metrics.get('market_cap'):,.0f}" if metrics.get("market_cap") else "Not available"},
        {"Metric": "Beta", "Value": f"{metrics.get('beta'):.2f}" if metrics.get("beta") is not None else "Not available"},
    ], use_container_width=True, hide_index=True)
    st.markdown(f"**Verified prudential overlay:** CET1 {percent(prudential.get('cet1_ratio'))} · RoTE {percent(prudential.get('rote'))}")
    st.markdown("#### Score contribution")
    st.dataframe([
        {"Metric": metric.replace("_", " ").title(), "Raw value": detail["raw_value"], "Percentile score": detail["percentile_score"], "Weight": f"{detail['weight']:.0%}"}
        for metric, detail in score.get("components", {}).items()
    ], use_container_width=True, hide_index=True)

with coverage_tab:
    st.subheader("EURO STOXX Banks universe")
    scored = {row["ticker"] for row in scores if row["status"] == "ranked"}
    st.caption(f"{len(scored)} of {len(universe)} banks currently have market-data screening scores.")
    st.dataframe([
        {"Bank": row.get("bank_name"), "Ticker": row.get("ticker"), "Country": row.get("country"), "Index weight": f"{row.get('weight_percent', 0):.2f}%", "Status": "Ranked" if row.get("ticker") in scored else "Insufficient provider data"}
        for row in universe
    ], use_container_width=True, hide_index=True)

with evidence_tab:
    st.subheader("Source evidence")
    selected = st.selectbox("Select a bank for evidence", [row["ticker"] for row in universe], key="evidence_bank")
    bank = banks.get(selected, {"official_evidence": []})
    st.link_button("Open official investor-relations reports", report_pages[selected])
    for item in bank.get("official_evidence", []):
        st.markdown(f"**{item['metric']}** — {item.get('note', 'Source observation')}  ")
        st.markdown(f"[Open official source]({item['source_url']})")
    if not bank.get("official_evidence"):
        st.info("Official prudential evidence is pending for this bank. Market fields are provider observations.")

with methodology_tab:
    st.subheader("Methodology and controls")
    st.markdown("**Common 23-bank score:** P/B 25%, P/E 15%, ROE 20%, ROA 10%, dividend yield 10%, earnings growth 10%, and revenue growth 10%. Lower valuation multiples score higher; higher returns, yield, and growth score higher. Percentile ranking limits the influence of extreme values.")
    st.markdown("**Official-report overlay:** CET1, leverage, LCR, NSFR, NPL ratio, NPL coverage, cost of risk, NIM, cost/income, loan/deposit ratio, and IRRBB sensitivities are included only when period-aligned evidence is available.")
    st.markdown("**Controls:** common reporting dates, source evidence, freshness checks, sensitivity analysis, and publication gate.")
    st.markdown("**Scope:** this is a research screening tool, not personalized investment advice.")
    report_path = BASE_DIR / "pilot_report.md"
    if report_path.exists():
        st.download_button("Download analyst report", report_path.read_text(encoding="utf-8"), "pilot_report.md", "text/markdown")
