# Cross-market and overnight factor batch v1

Separate, predeclared experiments across the 18 cached ETF pairs. No orders.

New lagged predictors: broad-market returns; small-cap relative strength;
semiconductor versus Nasdaq leadership; Nasdaq versus S&P leadership; bond
and gold moves; cross-market direction disagreement; prior-session intraday
and overnight decomposition; volume shock; closing-range position; trend-path
efficiency; short/long volatility ratio; gap-versus-session reversal interaction.
These test associations, not a claim that one market causally leads another.

Four feature ablations: prior price only; price plus behavior; price plus
cross-market context; all factors plus prior-day macro. Each uses ridge or
shallow Extra Trees with three net-profit cushions. Two holding intervals:
vendor daily open-to-close; vendor close-to-next-scheduled-session open.
**All predictors lag one full session even for close entries.** Today's gap,
closing price and volume never enter a forecast for today's assumed fill.
Missing next-session prices never bridge to a later date. Daily vendor prices
are not verified auction fills; overnight includes weekends and overnight risk.

Budget: 18 x 2 x 24 = 864 configurations. Selection uses expanding 2021/2022/
2023 predictions with a two-session training embargo. Existing 2024–September
2026 periods are already inspected diagnostics. Keep failed hypotheses, full
candidate rankings, feature snapshots and code SHA. No later-return cross-pair
winner selection. Daily results cannot be directly compared with intraday
results or interpreted as recovering stop/target paths. Allocation stays 10%;
slippage stress 5/10/20bps per side. No new service, subscription or API keys.

Surviving-fund selection, benchmark/proxy mismatches, daily fill assumptions,
multiple testing and missing market-data first-seen vintages remain limitations.
Any positive pocket still needs prospective predictions on genuinely new data.
