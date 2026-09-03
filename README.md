# EU Banks Picker

Production-oriented prototype of the **EuroSTOXX Bank Valuation Agent**.

It is designed for all 23 EURO STOXX Banks constituents. The current pilot
contains real observations for Crédit Agricole, BNP Paribas, and Deutsche Bank;
the remaining banks are added only after official report URLs are verified.

## Workflow

```text
Official reports -> PDF text/tables -> provenance archive
Market prices ---------------------> comparable dataset
                       -> quality/freshness gates
                       -> weighted peer score
                       -> cited report and Streamlit dashboard
```

## Run locally

```powershell
& ".\\venv\\Scripts\\python.exe" .\\run_pilot_pipeline.py
streamlit run .\\pilot_dashboard.py
```

## Production controls

- SHA-256 file hashes and page-level provenance
- Period and definition comparability checks
- Missing-data exclusion and freshness gates
- Evidence validation and weight sensitivity analysis
- Governance disclosures and human-review checklist

The metric catalogue covers valuation, profitability, capital, leverage,
liquidity, funding, asset quality, interest-rate, market, operational, and
systemic-importance indicators. See `metric_catalog.json`.

## Expand the universe

`bank_master.json` contains the 23-bank universe and `report_registry.json`
contains official report locations. Run the downloader to process every entry:

```powershell
& ".\\venv\\Scripts\\python.exe" .\\download_registered_reports.py
```

The resulting `download_manifest.json` records downloaded, pending, and failed
entries. No bank is scored until its metrics pass the comparability and evidence
gates.

## Streamlit deployment

Deploy `pilot_dashboard.py` from this repository using Streamlit Community
Cloud. Set the app entrypoint to `pilot_dashboard.py` and install dependencies
from `requirements.txt`.

This is a research screening tool, not personalized investment advice.
