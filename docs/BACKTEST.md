# Crypto Bot v4.4 — Backtesting Methodology

## Walk Forward Analysis

The Learning Service implements Walk Forward per the specification:

### Parameters
- **Training window**: 6 months
- **Test window**: 1 month
- **Step**: 1 month
- **Minimum stable windows**: 3

### Process
1. Train on months 1-6, test on month 7
2. Train on months 2-7, test on month 8
3. ...continue through all available data
4. Evaluate multi-criteria score for each window
5. Check stability: no window's score drops >30% from average

### Multi-Criteria Score
```
score = 0.35 × sharpe_norm + 0.25 × pf_norm + 0.20 × dd_norm + 0.20 × stability_norm
```

### Acceptance Criteria
- Profit Factor > 1.3 (with fees & slippage)
- No statistically significant degradation
- Works on 2+ market regimes
- Max drawdown within limits

## Running a Backtest
```python
from services.learning_service.service import LearningService
from datetime import datetime, timedelta

# Prepare trade history
trades = [...]  # list of dicts with timestamp, pnl

ls = LearningService()
results = ls.run_walk_forward(
    trades,
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2026, 1, 1),
)

for r in results:
    print(f"Window {r.window_index}: Score={ls.multi_criteria_score(r.metrics)}")
```
