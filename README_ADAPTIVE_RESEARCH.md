# Adaptive, cost-aware daily research v1

18 predeclared cached ETF pairs; no orders or new data subscription.

This batch changes the learning procedure instead of adding tickers. Models
refit each calendar quarter using either expanding history or the last 504
observed sessions, with two sessions embargoed before prediction. Features
remain prior-session only. The model targets realized returns at **10 bps per
side**, with labels clipped at training-only 1st/99th percentiles to reduce
sensitivity to a few extreme training days. Evaluation returns are never clipped.

Two decisions: average ridge/Extra Trees forecasts; trade only when both
models agree on the direction and each clears the same profit cushion.
Two feature groups: six lagged price variables; full context/behavior/macro
plus known weekday and distance to scheduled month/quarter end. Full-year
exchange schedules prevent a truncated dataset from inventing calendar ends.
Three post-cost cushions: 0%, .10%, .20% position return. Budget 432 configurations.

Ranking uses expanding/rolling causal quarterly predictions in 2021–2023
only, requiring 75 trades and 10 per development year, with penalties for
instability/drawdown. All 2024–September 2026 returns are already-inspected
diagnostics. Unlike frozen models, adaptive evaluation can train on past
quarters of that evaluation period; it never sees the predicted quarter's
outcomes. This is an explicitly different procedure, not fresh holdout evidence.

Primary cost: 10 bps/side; stress: 20 bps/side. Allocation: 10%. Same-window
always-bull/always-bear and cash controls; block bootstrap mean-return intervals
are unadjusted for multiple testing. Raw vendor daily opens/closes are still
hypothetical execution prices, not verified auction/quote fills. Surviving-fund
selection and imperfect proxies remain limitations. Every candidate ranking and
replay snapshot stays private with code SHA. Positive retrospective findings
still require genuinely new prospective predictions and execution validation.
