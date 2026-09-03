# EuroSTOXX Bank Valuation Agent

## Problem

Compare public financial information for EURO STOXX Banks constituents and
identify potentially attractive or expensive banks relative to peers.

The deployed dashboard ranks all 23 constituents using a common provider-data
screen based on P/B, P/E, ROE, ROA, dividend yield, earnings growth, and revenue
growth. It also displays price, forward P/E, book value per share, EPS, profit
margin, payout ratio, market capitalisation, and beta. Official prudential
metrics are added as a separate evidence-backed overlay as report coverage
expands, and every bank has an official investor-relations link.

The dark-mode dashboard presents all 23 ranking rows at once. It includes flag
images, country codes, tickers, index weights, euro-denominated prices, P/E,
P/B, ROE, dividend yield, scores, and concise comments. The Evidence tab is a
complete 23-bank directory of official annual and quarterly-report links.

Provider dividend yields arrive in percentage points and are divided by 100
before scoring, then converted back only for display (for example, provider
`5.63` → stored `0.0563` → displayed `5.63%`).

## Inputs

- Official quarterly and annual bank reports
- Page-level extracted evidence
- Market prices with retrieval timestamps
- Comparable banking and valuation metrics

## Workflow

```text
Official reports -> PDF extraction -> evidence archive
Market prices ---------------------> comparable dataset
                       -> quality/freshness gates
                       -> weighted peer score
                       -> cited Markdown report and dashboard
```

## Controls

- Period and definition comparability checks
- Missing-data exclusion
- Source and evidence validation
- Stale-price gate
- Weight sensitivity analysis
- Governance disclosures

## Run

```powershell
& "C:\FG\.venv\Scripts\python.exe" `
  "C:\FG\Roadmap to AI\run_pilot_pipeline.py"
streamlit run "C:\FG\Roadmap to AI\pilot_dashboard.py"
```

To monitor rollout coverage across all 23 constituents:

```powershell
& "C:\FG\.venv\Scripts\python.exe" `
  "C:\FG\Roadmap to AI\coverage_report.py"
```

The latest download run is recorded in `download_manifest.json`. The current
batch downloaded official PDFs for ACA, BNP, and DBK; the remaining entries are
pending URL verification.

This is a research screening tool, not personalized investment advice.
