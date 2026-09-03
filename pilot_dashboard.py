"""Small Streamlit view for the three-bank pilot."""

from pathlib import Path
from datetime import date, datetime, timezone
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


st.set_page_config(page_title="EuroSTOXX Bank Valuation Pilot", layout="wide")
st.title("EuroSTOXX Bank Valuation Agent — Pilot")
st.caption("Research screening tool; not personalized investment advice.")

if st.button("Refresh market data and rebuild report"):
    with st.status("Running pilot pipeline...", expanded=True) as status:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "run_pilot_pipeline.py")],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            status.update(label="Refresh complete", state="complete")
            st.cache_data.clear()
            st.rerun()
        status.update(label="Refresh failed", state="error")
        st.code(result.stdout + "\n" + result.stderr)

banks, scores = load_data()
st.subheader("Relative ranking")
price_dates = [
    bank.get("market_data", {}).get("price_date")
    for bank in banks.values()
    if bank.get("market_data", {}).get("price_date")
]
if price_dates:
    latest_price_date = max(price_dates)
    age_days = (date.today() - datetime.strptime(latest_price_date, "%Y-%m-%d").date()).days
    message = f"Market prices last retrieved: {latest_price_date} ({age_days} day(s) old)."
    if age_days > 3:
        st.error(message + " Refresh before analysis.")
    else:
        st.info(message)
st.dataframe(
    [
        {
            "Rank": rank,
            "Bank": row["bank_name"],
            "Ticker": row["ticker"],
            "Score": row["score"],
            "Metrics used": ", ".join(row["metrics_used"]),
        }
        for rank, row in enumerate(scores, start=1)
    ],
    use_container_width=True,
    hide_index=True,
)

selected = st.selectbox("Inspect a bank", [row["ticker"] for row in scores])
bank = banks[selected]
row = next(item for item in scores if item["ticker"] == selected)
st.subheader(bank["bank_name"])
st.write(f"Report period: {bank['period']} ({bank['report_date']})")
st.json({"metrics": bank["metrics"], "valuation": bank.get("valuation_metrics", {}), "score": row})

st.subheader("Evidence")
for item in bank.get("evidence", []):
    st.markdown(f"- [{item['metric']}]({item['source_url']}) — {item.get('note', '')}")

st.warning("Validate provider valuation observations against official filings before making any decision.")

report_path = BASE_DIR / "pilot_report.md"
dataset_path = BASE_DIR / "pilot_analysis_dataset.json"
if report_path.exists() or dataset_path.exists():
    st.subheader("Export")
    if report_path.exists():
        st.download_button(
            "Download Markdown report",
            data=report_path.read_text(encoding="utf-8"),
            file_name="pilot_report.md",
            mime="text/markdown",
        )
    if dataset_path.exists():
        st.download_button(
            "Download analysis dataset",
            data=dataset_path.read_text(encoding="utf-8"),
            file_name="pilot_analysis_dataset.json",
            mime="application/json",
        )
