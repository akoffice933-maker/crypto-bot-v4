# Crypto Bot v4.4 — Troubleshooting

## Common Issues

### Bot won't start
1. Check config file exists: `ls config/config_v4.4.1.yaml`
2. Verify Python version: `python --version` (need 3.10+)
3. Install dependencies: `pip install -r requirements.txt`

### "API unavailable" errors
1. Check network connectivity
2. Verify API keys are valid
3. If using testnet, confirm `BINANCE_TESTNET=true`
4. Check binance system status: https://status.binance.com

### High slippage
- Check `execution.max_slippage` in config
- Consider increasing `limit_timeout`
- Verify exchange liquidity for your pairs

### Recovery Mode stuck
- Recovery mode triggers at 8% drawdown
- Requires 3 consecutive winning trades + drawdown < 5% to exit
- Review your strategy performance

### Data validation errors
- "Excessive gaps": Check exchange API availability
- "Negative prices": Data corruption — re-fetch data
- "Duplicates": Usually harmless, auto-corrected

### Database issues
```bash
# Reset SQLite database
rm crypto_bot_v4.db
python -c "from core.database.db_manager import DatabaseManager; db=DatabaseManager(); db.connect(); db.create_all()"
```
