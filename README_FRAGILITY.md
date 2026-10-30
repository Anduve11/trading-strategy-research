# Frozen strategy fragility diagnostics v1

Paper diagnostics only. No new strategy/position size is selected, no capital
is moved, and no orders are submitted. Reuses immutable, checksummed sizing
replays for all 18 pairs and both already-selected incumbent/challenger signals.

Evaluate 2024 separately from 2025–September 2026, at 10/50/100% allocations:

- Remove the top 1/3/5 positive position-return sessions. This hindsight
  intervention measures luck concentration; it is not a trading rule.
- Delay the signal by one/two eligible observations, retaining actual ETF
  outcome prices. This is not a model of minute-level execution latency.
- Miss 10%/25% of signals randomly, 1,000 fixed-seed trials; report endpoint
  return distribution and negative-return frequency under that simulation.
- Circularly shift frozen directions against actual outcomes, preserving
  direction frequency/pattern. Report descriptive comparison distributions;
  these are NOT valid post-selection significance p-values.
- Separate bull and inverse contributions; show quarterly P&L, top-three
  share of positive position returns, 10/20bps costs, and five-day block
  bootstrap mean-return intervals including cash days.

All results use already-inspected history. Bootstrap intervals are unadjusted
for extensive strategy/universe selection. Daily vendor fills and daily-close
drawdowns omit auction/quote validation, intraday losses and size impact.
High-allocation historical gains amplify these limitations and drawdowns;
they do not establish a scalable or prospective trading edge. Full diagnostics
and source references stay private, with failures and unfavorable tests retained.
