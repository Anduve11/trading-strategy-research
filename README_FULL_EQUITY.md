# Full-equity paper research

The user requested testing **100% of current account equity on each qualifying
trade**. This is the primary allocation for this study; 10% remains a comparison.
There are no real orders, fund transfers, account borrowing, or broker changes.
No signal means cash. Entry uses observed vendor daily open and exit observed
vendor daily close under stated adverse-price assumptions. Equity compounds
trade by trade. A 10%-allocation cumulative return is never multiplied by ten.

## Declared scope

18 independent ETF-pair accounts, each replaying 36 family rules, the 12 prior
reversal rules, and the frozen adaptive incumbent: **882 single-position
replays**. Returns are reported at 10% and 100% allocation and 10/20/50bps costs
per side. Cost 50bps is derived algebraically from the same observed close/open
ratio underlying the 10bps outcome. It is a fill-assumption stress, not a claim
about observed bid/ask spreads.

Four new full-equity policy comparisons per pair (**72 total**):

- Development growth: eligible rule with greatest mean daily log growth at
  100% equity and 20bps in 2021-2023; 75 trades and 10 per development year.
- Development fold resilience: same eligibility, worst annual return + 0.25
  mean annual return - 0.5 worst annual drawdown magnitude, measured at 100%
  equity and 20bps in 2021-2023.
- Quarterly growth: rerank the 48 declared rules with up to 504 earlier
  eligible observations, 250 observations minimum and two-observation embargo;
  require 40 historical trades, use 20bps mean daily log growth, and fix the
  choice before the evaluation quarter.
- Active-weight family ensemble: preserve previously frozen family choices,
  split 100% of equity equally among active legs, and remain cash if none act.

Both growth selectors and fold resilience hold cash when no eligible score is
positive. Risk acceptance does not create a positive historical growth score.
There is no later-period threshold tuning.

Two frozen policy controls per pair (**36 controls**) preserve the preceding
family ensemble and quarterly selections. The fixed-slot ensemble control
keeps unused slots in cash, even when its budget is 100%. It is explicitly
different from the active-weight ensemble, which deploys 100% whenever active.
Opposing bull/inverse legs each retain their own real ETF outcome and costs;
no order netting is assumed. No combined policy can exceed one account's equity.
Independent per-pair account returns cannot be added into one portfolio.

## Evidence and audit

Use exact sizing source commit `c599c70dda70af030e7f0627712e30ab4287ee98` and
family source commit `683bb5438174f622e5b7f18edb8f6b8d26ca3693`, verifying identical
source lineage and snapshot SHA256 before replay. Private artifacts retain
all growth/fold rankings, quarter-by-quarter choices, signal directions,
manifest hashes, and complete results including losses.

Report 2024, January 2025-September 2026, and combined 2024-September 2026, plus
development history. Risks include worst daily account return, losing-trade
streak, daily-close drawdown, sessions at drawdowns of 25/50/75/90%, recovery
gain needed, and any fall below half initial equity. Full-equity diagnostics
remove the best one/three/five winning sessions with hindsight and show quarters.
These observed frequencies are not forward loss probabilities.

## Limitations

100% account allocation to leveraged ETFs can entail very large underlying
exposure. Daily-close drawdown misses intraday losses, and the vendor open and
close remain hypothetical fills. Market impact at a particular dollar size,
actual spreads, taxes, commissions beyond modeled costs, and idle-cash yield
are unmodeled. No fresh holdout or prospective record is established: all
2024-2026 history has already been inspected, and repeated research can select
historical luck. User risk tolerance changes the research sizing and objectives;
it does not establish an edge or promise wealth.

Run `python scripts/full_equity_research.py --all` with existing private archive
credentials, or `--pair semiconductors`. The workflow tests once, processes
all pairs, preserves failures in its status/logs, and prints no numeric results
or credentials. This study changes only research, not live execution.
