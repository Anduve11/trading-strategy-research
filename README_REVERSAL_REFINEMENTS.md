# Reversal refinements (paper only)

The frozen fragility batch completed for all 18 pairs. Semiconductor reversal and
adaptive candidates depend on a few large winning sessions and weakened in the
last two inspected quarters. This motivates a small, explicit grid rather than
claiming that sizing has established an edge.

Run `python scripts/reversal_research.py --pair semiconductors` using the existing
private archive credentials. It verifies the immutable sizing replay checksum.

The 216-hypothesis budget is 18 pairs times thresholds 0.75, 1.0, 1.25 prior daily
volatility units times four filters: both directions, bull only, trend aligned,
and low directional efficiency (absolute prior efficiency below 0.3). Volatility
uses the existing lagged annualized proxy measure divided by sqrt(252), floored
at 0.1% daily. A prior loss below the negative threshold buys the bull ETF; a
prior gain above the positive threshold buys its inverse. Hold vendor open to
close for one session. No missing prices are filled.

Select only on 2021, 2022 and 2023 at 10% allocation and **20bps per side**.
Require 75 total trades and 10 each year. Score is worst annual return plus
0.25 times mean annual return minus 0.5 times worst annual drawdown magnitude.
Retain every candidate's results at both 10 and 20bps, including failures and
neighboring thresholds. An eligible selection can still be unprofitable.

2024 and 2025–September 2026 are already inspected historical diagnostics.
This grid was motivated by those results, so even development-only selection
does not make the later period an independent holdout. No significance or live
profitability claim follows. Real auction/quote verification, intraday loss
measurement and prospective paper predictions remain outstanding. No capital
or trading-account setting is changed.
