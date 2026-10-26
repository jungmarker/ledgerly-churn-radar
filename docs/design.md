# Design notes

## Decision and contract

Which twenty customers should Customer Success review first?

Completed weekly usage → account-cutoff features → next-90-day churn labels → temporal/account-separated model evaluation → ranked outreach queue.

The input contract is the Ledgerly raw CSV/schema documented in the pinned source repository. Monetary values are USD, dates refer to the synthetic company calendar and the snapshot is September 30, 2026. Reads are local and source files are never modified. Missing or malformed required columns fail visibly rather than silently inventing input fields.

## Evaluation

A deterministic account hash holds out 20% of customers. Training observations end September 2025; tests occur March/June 2026. Only completed weeks contribute usage. Missing history is imputed using training values and missingness indicators.

Average precision versus prevalence, ROC-AUC, Brier score, precision/recall among the twenty highest-risk accounts.

The tests use small constructed examples to catch cutoff leakage, incorrect identity decisions, review bypasses or revenue reconciliation errors. They do not merely assert that the pipeline runs. The full seeded pipeline runs in CI to expose schema and integration failures.

## Operator workflow

Run the analysis, read metrics.json, inspect detailed CSV exceptions or predictions, and review the narrative before taking a business action. Reruns replace the reports in the selected output folder. Save previous output folders if you need historical runs. Data is regenerated from the pinned source; no credentials are required for local analysis.

## Production changes

Use source contracts and historical snapshots, least-privilege storage, access controls, execution logging, retry/idempotency policies and data freshness monitoring. Separate feature generation from labeled evaluation and version both data and model configuration. Validate on representative real data before setting business thresholds. This demo uses local files and full rebuilds at about a few thousand accounts; it is not a benchmark of distributed scale.

## Known limitations

Predicted churn is not a causal uplift score: contacting a customer may not prevent churn. Repeated account observations make row-level confidence intervals inappropriate. No survival model, cost optimization, calibrated intervention benefit or health diagnosis. Future subscription end dates define at-risk eligibility and labels, never features.

## Interview walkthrough

1. Explain the business question and the input table grain.
2. Reproduce the report and trace one result to its source rows.
3. Explain the baseline, failure cases and why the evaluation split is appropriate.
4. Show the adversarial unit test and make a small behavior change.
5. Describe the changes needed for reliable operation on real company data.
