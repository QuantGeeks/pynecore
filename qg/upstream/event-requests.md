# `request.earnings` / `request.dividends` / `request.splits` read supplied events (6.10.10-qg.8)

**PyneCore version:** 6.10.10 (measured on `6.10.10-qg.7`).

## The problem

All three returned na (or raised `NotImplementedError` without `ignore_invalid_symbol`) on every bar; there was
no way to give the runner the data.

## The change

`ScriptRunner(..., event_data={"[EXCHANGE:SYMBOL:]KIND": rows})`, kind `earnings` / `dividends` / `splits`, rows
mappings with `time` (UTC ms or datetime) and the kind's fields (earnings `actual` `estimate` `standardized`;
dividends `gross` `net`; splits `numerator` `denominator`). A symbol-qualified key wins; a bare kind key serves
the chart's own symbol. Semantics (`pynecore/core/event_data.py`): events are a DAILY series merged like a daily
`request.security` series, the row's day taken in the exchange timezone: `lookahead_off` shows it from the last bar
of its day (`session.islastbar`), `lookahead_on` from the first; `gaps_off` holds the latest visible row, na before
the first; `gaps_on` shows it on the one bar it becomes visible. Several rows on a day: the latest wins. `currency`
is ignored. With no `event_data` (or no series for the requested symbol) behavior is unchanged.
State lives in `request._event_data`, swapped per runner like the other module state; `qg/gates/inventory.json`
carries the new paths.

## Tests

`qg/tests/test_event_data.py`: hourly chart, two earnings rows, one dividend, one split; all four gaps/lookahead
combinations hour by hour, the fields, key resolution, other symbols, no data.

## Not settled

The daily-series merge rule is inferred from how TradingView sources these feeds (daily corporate-action series
read through `request.security`); the reference gives parameters and field names, not the intraday timing, and no
TradingView export of these requests was available. `gaps_on` compares the bar with the previous bar the series
was READ on. Not filed (sev, 2026-10-31): nothing is pushed upstream.
