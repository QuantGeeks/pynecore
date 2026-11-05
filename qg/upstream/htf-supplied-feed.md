# Same-symbol HTF `request.security`: a supplied feed is the source of closed periods (6.10.10-qg.8)

**PyneCore version:** 6.10.10 (measured on `6.10.10-qg.7`).

## The problem (synthetic)

```pine
plot(request.security(syminfo.tickerid, "1D", close[1], lookahead = barmerge.lookahead_on))
```

on an hourly chart with a `1D` feed supplied through `security_data`. `lookahead_on` runs the developing
transport: the chart aggregates its own bars into the containing HTF bar and pushes it to the context, and the
bar it pushes when a period CLOSES was the chart's aggregate too. The supplied feed was read only for the periods
before the chart's first bar. Chart's last hourly close of day 0 = 1023, the feed's official close = 5000:
`close[1]` on day 1 read 1023.

## The change

For a same-symbol HTF context with `lookahead_on` and a feed the caller supplied (not the chart's own feed), the
feed's bars are indexed on the context's period grid (`load_official_htf_bars`), and a period that closes is
delivered as the feed's bar (`official_closed_bar`) in both transports: the per-bar closed step and the planned
historical developing batch (`DevBatchSpec.official_bars`). The developing period stays chart-built, so
PyneCore still does not reproduce `lookahead_on`'s future read of a bare `close`; `close[1]` is TradingView's.
No supplied feed: unchanged (an intraday context is aggregated from the chart's feed; a D/W/M context is
refused with the `security_data` hint). Documented in `request.security`'s docstring.

## Tests

`qg/tests/test_htf_feed.py`: hourly 24/7 chart, daily feed with OHLC unlike the hourly aggregate;
`lookahead_on` `close[1]` and `high[1]`, `gaps_on`, `lookahead_off` current and `[1]`, both transports; no feed:
D refused, intraday chart-built.

## Not settled

`gaps_on` with `lookahead_on` holds the value through the period here (pre-existing); not compared with TradingView.
Not filed (sev, 2026-10-31): nothing is pushed upstream.
