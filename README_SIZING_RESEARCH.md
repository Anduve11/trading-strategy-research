# Capital sizing and simple-rule challengers v1

Research only. No money is moved; no order or account setting is changed.
Adding starting dollars changes dollar P&L but not percentage return under
unchanged fill assumptions. Raising allocation changes both gains and losses.

Reconstruct each of 18 frozen adaptive incumbents from its explicit selected
parameters, immutable source snapshot and source code SHA. Add five signal
challengers: bull/cash trend, two-way momentum, one-sigma one-day reversal,
prior-close range breakout, and trend/reversal regime switching. Select a rule
using 2021–2023 only, requiring sufficient trades per development year and
penalizing instability/drawdown. New signal budget: 90 hypotheses. Keep failures.

For incumbent, development-selected challenger and same-window always-bull,
report predeclared 10/25/50/100% capital allocation and a 10% annual volatility
target capped at 100%. Volatility sizing uses prior proxy volatility times
stated leverage, an approximation. Ten and twenty bps per-side cost scenarios
are recomputed from actual observed daily returns, not linear multiplication
of aggregate backtest returns. Show full compounding, daily-close drawdown,
capital deployed, activity, CAGR and hypothetical $10k/$100k ending balances.
Position-sizing scenarios are diagnostics, not additional alpha evidence.

No account borrowing is modeled; 100% in a leveraged ETF can still imply 200%
or 300% underlying exposure. Drawdowns omit intraday troughs; trade size impact
on spreads/fills is unmodeled. Vendor daily prices remain hypothetical fills.
2024–September 2026 data are inspected historical diagnostics; no allocation
or cross-pair winner is selected using those outcomes. Prospective validation
and executable-price evidence remain necessary. Snapshots/results stay private.
