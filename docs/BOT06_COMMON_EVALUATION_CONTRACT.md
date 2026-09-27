# BOT-06 Common Strategy Evaluation Contract

BOT-06 gives the bot programme one deterministic, machine-readable contract for
strategy evaluation. It does **not** run the strategy tournament and it does not
change any strategy rule or parameter.

## Candidate surface

The common registry exposes 18 fixed candidates:

- the 14 existing internal fixed-rule strategies already present in
  `STRATEGIES`;
- the existing M1/M5 `trend_scalper`;
- the three pinned XAU-60 adapters: SMC Scalper v2.1, Trend Break + Trauma +
  RSI v2.1, and CRT + TBS v2.1.

Every entry declares an evaluation timeframe, input columns, warm-up,
statefulness, source, symbol restriction where applicable, context timeframes,
and that parameters are frozen.

The 14 legacy fixed-rule strategies use M1 as the **evaluation normalization**
because that is the existing common historical-runner convention. This does not
claim that their underlying rule intrinsically requires M1.

## Fresh-run isolation

`build_evaluation_strategy()` always creates a new strategy instance.
Stateful daily/session strategies are therefore not reused across instruments,
years, folds, or independent tournament runs.

## XAU-60 adaptation

The XAU-60 bridge performs only interface adaptation:

- canonical symbol remains exactly `XAUUSD`;
- `tick_volume` is copied to the upstream `volume` field;
- any source-declared auxiliary column such as SMC `spread` must already be
  supplied by the tournament data adapter;
- the upstream adapter sees only the completed current candle and
  `observed_at = candle_open + timeframe`;
- `SignalProposal` is converted to the existing non-executing
  `TradeIntent`.

No stop, target, filter, session, or parameter is altered.

## Trend scalper adaptation

The trend scalper is explicitly marked as M1 primary plus M5 context. Its
factory refuses to build unless M5 context candles and a positive instrument
point are supplied.

## Safety and scope

BOT-06 contains no broker order path, no DEMO/LIVE toggle, no market-data
acquisition, no parameter search, no result-based mutation, and no access to
protected holdout data.

BOT-07 can now build the tournament harness against this registry without
special-casing strategy construction.
