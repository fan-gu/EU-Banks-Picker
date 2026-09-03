"""User-facing Streamlit dashboard for the EuroSTOXX bank pilot."""

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
    with (BASE_DIR / "pilot_analysis_dataset.json").open(encoding="utf-8") as handle:
        banks = {row["ticker"]: row for row in json.load(handle)}
    with (BASE_DIR / "pilot_scores.json").open(encoding="utf-8") as handle:
        scores = json.load(handle)
    return banks, scores


def percent(value):
    return f"{value:.1%}" if isinstance(value, (int, float)) else "Not available"


def multiple(value):
    return f"{value:.2f}x" if isinstance(value, (int, float)) else "Not available"


st.set_page_config(page_title="EU Banks Picker", page_icon="🏦", layout="wide")
st.title("EU Banks Picker")
st.caption("EuroSTOXX Bank Valuation Agent · relative-value research screening")

if st.button("Refresh data"):
    with st.status("Refreshing pilot data...", expanded=False) as status:
        result = subprocess.run([sys.executable, str(BASE_DIR / "run_pilot_pipeline.py")], cwd=BASE_DIR, capture_output=True, text=True)
        if result.returncode == 0:
            status.update(label="Refresh complete", state="complete")
            st.cache_data.clear()
            st.rerun()
        status.update(label="Refresh failed", state="error")
        st.code(result.stderr or result.stdout)

banks, scores = load_data()
ranking_tab, details_tab, evidence_tab, methodology_tab = st.tabs(["Relative ranking", "Bank details", "Evidence", "Methodology"])

with ranking_tab:
    st.subheader("Relative ranking")
    prices = [bank.get("market_data", {}).get("price_date") for bank in banks.values() if bank.get("market_data", {}).get("price_date")]
    if prices:
        latest = max(prices)
        age = (date.today() - datetime.strptime(latest, "%Y-%m-%d").date()).days
        (st.error if age > 3 else st.info)(f"Market prices: {latest} ({age} day(s) old)." + (" Refresh before analysis." if age > 3 else ""))
    st.dataframe([
        {"Rank": i, "Bank": row["bank_name"], "Ticker": row["ticker"], "Screening score": row["score"], "Metrics used": ", ".join(row["metrics_used"]) or "None"}
        for i, row in enumerate(scores, 1)
    ], use_container_width=True, hide_index=True)
    st.warning("A higher score indicates stronger relative inputs under this methodology; it is not a buy or sell recommendation.")

with details_tab:
    selected = st.selectbox("Select a bank", [row["ticker"] for row in scores])
    bank = banks[selected]
    score = next(row for row in scores if row["ticker"] == selected)
    st.subheader(f"{bank['bank_name']} ({selected})")
    st.write(f"Reporting period: **{bank['period']}** · date: **{bank['report_date']}**")
    metrics = bank.get("metrics", {})
    valuation = bank.get("valuation_metrics", {})
    cols = st.columns(5)
    cols[0].metric("Screening score", score["score"] if score["score"] is not None else "N/A")
    cols[1].metric("CET1", percent(metrics.get("cet1_ratio")))
    cols[2].metric("RoTE / RoE", percent(metrics.get("rote") or metrics.get("roe")))
    cols[3].metric("P/B", multiple(valuation.get("price_to_book")))
    cols[4].metric("P/E", multiple(valuation.get("price_to_earnings")))
    st.markdown("#### Score contribution")
    st.dataframe([
        {"Metric": metric, "Raw value": detail["raw_value"], "Normalized score": detail["normalized_score"], "Weight": f"{detail['weight']:.0%}"}
        for metric, detail in score.get("contributions", {}).items()
    ], use_container_width=True, hide_index=True)

with evidence_tab:
    st.subheader("Source evidence")
    selected = st.selectbox("Select a bank for evidence", [row["ticker"] for row in scores], key="evidence_bank")
    bank = banks[selected]
    for item in bank.get("evidence", []):
        st.markdown(f"**{item['metric']}** — {item.get('note', 'Source observation')}  ")
        st.markdown(f"[Open official source]({item['source_url']})")
    st.info("Evidence links are retained for review; provider valuation fields require confirmation against official filings.")

with methodology_tab:
    st.subheader("Methodology and controls")
    st.markdown("**Scoring:** CET1 40%, P/B 35%, P/E 25%. Lower valuation multiples score higher; missing metrics are excluded and remaining weights are renormalized.")
    st.markdown("**Controls:** common reporting dates, source evidence, freshness checks, sensitivity analysis, and publication gate.")
    st.markdown("**Scope:** this is a research screening tool, not personalized investment advice.")
    report_path = BASE_DIR / "pilot_report.md"
    if report_path.exists():
        st.download_button("Download analyst report", report_path.read_text(encoding="utf-8"), "pilot_report.md", "text/markdown")
