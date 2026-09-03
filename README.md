# MT5 Scalping Agent

A safety-first foundation for research and backtesting of deterministic trading strategies. The default runtime mode is `BACKTEST`.

## Safety boundary

- No live trading is implemented or enabled.
- Signals and execution will remain separated by a risk engine.
- Credentials belong only in a local `.env` file, which is ignored by Git.
- Every future broker response must be verified before it is treated as an execution.

## Project layout

`src/mt5_scalping_agent` contains application code, organised by responsibility. `tests` contains automated tests. Runtime-generated SQLite data, logs, and reports are deliberately kept out of version control.

## Intended setup

Use Python 3.12 to create a workspace-local virtual environment, then install the project with its development dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

MT5 terminal installation and broker login are not part of this phase.

- Configuration recognizes `BACKTEST`, `DEMO`, and `LIVE`, but order submission is
  blocked in every mode until a reviewed execution phase explicitly implements it.


## Research strategy baseline

`TrendScalper` is a deterministic research proposal, not a profitable or executable strategy. Its documented baseline requires M1/M5 EMA 9/21 trend alignment, M1 MACD confirmation, bounded RSI, a spread no higher than 3 points, fresh candles, and the 07:00-20:00 UTC session. These values are configuration defaults covered by tests and must be validated through backtests before any demo execution work.

## Risk-engine baseline

`RiskEngine` is the final decision authority for a trade plan and has no MT5 execution method. Its research defaults are 0.5% equity risk per trade, 2% maximum daily loss, 10% maximum drawdown, three consecutive losses, one open position, one lot maximum exposure and position size, 1.5 minimum reward/risk, and three points maximum spread. It sizes volume from account equity, stop-loss distance, and the broker's tick size/value and volume constraints. These are documented starting controls, not validated trading settings; they must be tested in backtests and demo operation before any execution phase.

## Backtesting foundation

`CandleBacktester` accepts validated historical candles and a strategy callback that returns a stop/target `TradeIntent`. The callback receives data only through the current candle close; any intent enters on the next candle open, avoiding look-ahead bias. The simulator accepts explicit spread, slippage, and per-lot-per-side commission assumptions, uses a conservative stop-loss outcome when a candle reaches both target and stop, and passes each simulated trade through `RiskEngine`. It reports trades, rejected intents, an equity curve, net profit, win rate, profit factor, and maximum drawdown. The current signal-only strategy does not yet define stops and targets, so it is deliberately not backtested as a trade-generating strategy.

## Strategy exits

An actionable `TrendScalper` proposal now contains an indicative entry, stop loss, and take profit. The research baseline places a stop one M1 ATR from entry and a target two M1 ATRs from entry, yielding a nominal 2:1 reward/risk before transaction costs. `SignalProposal` validates this price geometry, and `TradeIntent.from_signal()` converts only actionable proposals for the backtester. ATR multiples are configuration values covered by tests, not validated profitability parameters.

hey