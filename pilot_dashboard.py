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
COUNTRY_INFO = {
    "Austria": ("AT", "at"), "Belgium": ("BE", "be"),
    "Finland": ("FI", "fi"), "France": ("FR", "fr"),
    "Germany": ("DE", "de"), "Ireland": ("IE", "ie"),
    "Italy": ("IT", "it"), "Netherlands": ("NL", "nl"),
    "Spain": ("ES", "es"),
}


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
    evidence_path = BASE_DIR / "table_evidence_index.json"
    table_evidence = (
        json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence_path.exists()
        else {"source_count": 0, "table_count": 0, "documents": []}
    )
    return banks, scores, universe, report_pages, table_evidence


def percent(value):
    return f"{value:.1%}" if isinstance(value, (int, float)) else "Not available"


def multiple(value):
    return f"{value:.2f}x" if isinstance(value, (int, float)) else "Not available"


def decimal(value):
    return f"{value:.2f}" if isinstance(value, (int, float)) else "Not available"


def short_comment(score):
    if score is None:
        return "Insufficient comparable data"
    if score >= 67:
        return "Strong relative screen"
    if score >= 45:
        return "Mixed; broadly mid-pack"
    return "Weak relative screen"


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

banks, scores, universe, report_pages, table_evidence = load_data()
ranking_tab, details_tab, coverage_tab, evidence_tab, methodology_tab = st.tabs(["Relative ranking", "Bank details", "Universe coverage", "Evidence", "Methodology"])

with ranking_tab:
    st.subheader("Relative ranking")
    timestamps = [bank.get("retrieved_at") for bank in banks.values() if bank.get("retrieved_at")]
    if timestamps:
        latest = max(timestamps)
        observed = datetime.fromisoformat(latest.replace("Z", "+00:00")).date()
        age = (date.today() - observed).days
        (st.error if age > 3 else st.info)(f"Provider data retrieved: {observed} ({age} day(s) old)." + (" Refresh before analysis." if age > 3 else ""))
    ranking_rows = []
    for i, row in enumerate((item for item in scores if item["status"] == "ranked"), 1):
        bank = banks[row["ticker"]]
        metrics = bank.get("metrics", {})
        country_code, flag_code = COUNTRY_INFO.get(bank["country"], (bank["country"], ""))
        ranking_rows.append({
            "Rank": i,
            "Flag": f"https://flagcdn.com/w40/{flag_code}.png" if flag_code else "",
            "Country": country_code,
            "Bank": row["bank_name"],
            "Ticker": row["ticker"],
            "Index weight": bank.get("weight_percent"),
            "Current price": metrics.get("price"),
            "P/E": metrics.get("price_to_earnings"),
            "P/B": metrics.get("price_to_book"),
            "ROE": metrics.get("return_on_equity") * 100 if metrics.get("return_on_equity") is not None else None,
            "Div. yield": metrics.get("dividend_yield") * 100 if metrics.get("dividend_yield") is not None else None,
            "Score": row["score"],
            "Comment": short_comment(row["score"]),
        })
    st.dataframe(
        ranking_rows,
        width="stretch",
        hide_index=True,
        height=845,
        column_config={
            "Flag": st.column_config.ImageColumn("", width="small"),
            "Index weight": st.column_config.NumberColumn("Index wt.", format="%.2f%%"),
            "Current price": st.column_config.NumberColumn("Price", format="€%.2f"),
            "P/E": st.column_config.NumberColumn("P/E", format="%.2fx"),
            "P/B": st.column_config.NumberColumn("P/B", format="%.2fx"),
            "ROE": st.column_config.NumberColumn("ROE", format="%.1f%%"),
            "Div. yield": st.column_config.NumberColumn("Div. yield", format="%.1f%%"),
            "Score": st.column_config.NumberColumn("Score", format="%.1f"),
        },
    )
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
        {"Metric": "Book value per share", "Value": decimal(metrics.get("book_value_per_share"))},
        {"Metric": "Earnings per share", "Value": decimal(metrics.get("earnings_per_share"))},
        {"Metric": "Return on assets", "Value": percent(metrics.get("return_on_assets"))},
        {"Metric": "Profit margin", "Value": percent(metrics.get("profit_margin"))},
        {"Metric": "Payout ratio", "Value": percent(metrics.get("payout_ratio"))},
        {"Metric": "Earnings growth", "Value": percent(metrics.get("earnings_growth"))},
        {"Metric": "Revenue growth", "Value": percent(metrics.get("revenue_growth"))},
        {"Metric": "Market capitalization", "Value": f"{metrics.get('market_cap'):,.0f}" if metrics.get("market_cap") else "Not available"},
        {"Metric": "Beta", "Value": f"{metrics.get('beta'):.2f}" if metrics.get("beta") is not None else "Not available"},
    ], width="stretch", hide_index=True)
    st.markdown(f"**Verified prudential overlay:** CET1 {percent(prudential.get('cet1_ratio'))} · RoTE {percent(prudential.get('rote'))}")
    st.markdown("#### Score contribution")
    st.dataframe([
        {"Metric": metric.replace("_", " ").title(), "Raw value": detail["raw_value"], "Percentile score": detail["percentile_score"], "Weight": f"{detail['weight']:.0%}"}
        for metric, detail in score.get("components", {}).items()
    ], width="stretch", hide_index=True)

with coverage_tab:
    st.subheader("EURO STOXX Banks universe")
    scored = {row["ticker"] for row in scores if row["status"] == "ranked"}
    st.caption(f"{len(scored)} of {len(universe)} banks currently have market-data screening scores.")
    st.dataframe([
        {"Bank": row.get("bank_name"), "Ticker": row.get("ticker"), "Country": row.get("country"), "Index weight": f"{row.get('weight_percent', 0):.2f}%", "Status": "Ranked" if row.get("ticker") in scored else "Insufficient provider data"}
        for row in universe
    ], width="stretch", hide_index=True)

with evidence_tab:
    st.subheader("Official financial reports")
    st.caption("Links open official issuer reporting pages where the latest publication is maintained.")
    st.dataframe(
        [
            {
                "Bank": row["bank_name"],
                "Ticker": row["ticker"],
                "Annual report": report_pages[row["ticker"]]["annual"],
                "Quarterly / interim": report_pages[row["ticker"]]["quarterly"],
            }
            for row in universe
        ],
        width="stretch",
        hide_index=True,
        height=845,
        column_config={
            "Annual report": st.column_config.LinkColumn("Latest annual report", display_text="Open annual reports"),
            "Quarterly / interim": st.column_config.LinkColumn("Latest quarterly / interim", display_text="Open results"),
        },
    )

    st.markdown("#### Extracted table evidence")
    st.caption(
        f"{table_evidence.get('table_count', 0)} metric-relevant table candidates "
        f"from {table_evidence.get('source_count', 0)} locally processed official reports. "
        "Candidates are excluded from ranking until their definition, period, unit and scope are reviewed."
    )
    evidence_documents = [
        document for document in table_evidence.get("documents", []) if document.get("tables")
    ]
    if not evidence_documents:
        st.info("No structured table evidence has been generated yet.")
    else:
        evidence_tickers = [document["ticker"] for document in evidence_documents]
        selected_evidence_ticker = st.pills(
            "View extracted evidence for",
            evidence_tickers,
            default=evidence_tickers[0],
            key="evidence_bank",
        )
        selected_document = next(
            (document for document in evidence_documents if document["ticker"] == selected_evidence_ticker),
            evidence_documents[0],
        )
        st.write(
            f"**{selected_document.get('bank_name') or selected_document['ticker']}** · "
            f"{selected_document['document']} · {selected_document['table_count']} retained table(s)"
        )
        for table in selected_document["tables"]:
            metric_label = ", ".join(
                metric.replace("_", " ").upper() for metric in table["matched_metrics"]
            )
            with st.expander(
                f"Page {table['page']} · {metric_label} · review pending",
                icon=":material/table_view:",
            ):
                image_path = BASE_DIR / table["evidence_image"] if table.get("evidence_image") else None
                if image_path and image_path.exists():
                    st.image(image_path, caption=f"Source table on PDF page {table['page']}")
                st.dataframe(table.get("rows", []), width="stretch", hide_index=True)
                st.caption(table.get("page_excerpt", ""))
                if table.get("source_url"):
                    st.link_button(
                        "Open official source",
                        table["source_url"],
                        icon=":material/open_in_new:",
                    )

with methodology_tab:
    st.subheader("Methodology and controls")
    st.markdown("**Common 23-bank score:** P/B 25%, P/E 15%, ROE 20%, ROA 10%, dividend yield 10%, earnings growth 10%, and revenue growth 10%. Lower valuation multiples score higher; higher returns, yield, and growth score higher. Percentile ranking limits the influence of extreme values.")
    st.markdown("**Official-report overlay:** CET1, leverage, LCR, NSFR, NPL ratio, NPL coverage, cost of risk, NIM, cost/income, loan/deposit ratio, and IRRBB sensitivities are included only when period-aligned evidence is available.")
    st.markdown("**Controls:** common reporting dates, source evidence, freshness checks, sensitivity analysis, and publication gate.")
    st.markdown("**Scope:** this is a research screening tool, not personalized investment advice.")
    report_path = BASE_DIR / "pilot_report.md"
    if report_path.exists():
        st.download_button("Download analyst report", report_path.read_text(encoding="utf-8"), "pilot_report.md", "text/markdown")
