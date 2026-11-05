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

## Known differences from TradingView (approximations, not measured)

* **Release time.** TradingView's manual says these values "reflect the data available as it comes in", i.e. at
  the release. This module merges a daily series: `lookahead_off` shows an event from the END of its calendar day,
  `lookahead_on` from the START of it. An after-hours report therefore appears on the day's last bar, not at the
  release minute, and the first bar of the day sees it under `lookahead_on`.
* **Timezone.** The day of an event (and of a bar) is taken in the CHART symbol's exchange timezone, also for a
  series requested for another symbol whose exchange runs in a different zone.
* **Currency.** The `currency` argument is accepted and ignored; values are returned as supplied.
* **Charts coarser than 1D.** A bar sees every event up to its last calendar day (the day before the next bar
  opens, the next open being the chart's expected one), so `lookahead_on` and `lookahead_off` agree there.
* **Splits** have no default field (Pine has none either): without one the request is na.
* **Which bars ask** does not matter: the previous and next bars come from the chart, so a request inside an `if`
  returns what a request on every bar returns on the bars it runs.

## Not settled

The daily-series merge rule is inferred from how TradingView sources these feeds (daily corporate-action series
read through `request.security`); the reference gives parameters and field names, not the intraday timing, and no
TradingView export of these requests was available. Not filed (sev, 2026-10-31): nothing is pushed upstream.
