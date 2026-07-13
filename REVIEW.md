# 🔍 Code Review: crypto-bot-v4

**Репозиторий**: [github.com/akoffice933-maker/crypto-bot-v4](https://github.com/akoffice933-maker/crypto-bot-v4)  
**Версия**: 4.4.1 · **Коммит**: `3a48235`  
**Дата**: 13.07.2026  
**Файлов**: 52 `.py` · **Строк**: 8 196 · **Тестов**: 94/94 ✅  

---

## 📊 Итоговая оценка

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| **Архитектура** | ★★★★★ | 13+1 сервисов, слабая связность, DI, Online/Offline |
| **Корректность** | ★★★★☆ | Критические баги исправлены; остались acceptable trade-offs |
| **Безопасность** | ★★★★☆ | Токен/HMAC webhook, шифрование API-ключей; нет rate-limit на HTTP |
| **Тестирование** | ★★★★★ | 94 теста, 0 warnings, покрыты все критические пути |
| **Документация** | ★★★★★ | 2 README (EN/RU), 7 docs, docstrings на английском |
| **Читаемость кода** | ★★★★☆ | PEP 8, structlog, type hints; 2 метода с цикломатической сложностью >10 |
| **Производительность** | ★★★★☆ | Векторизованный ADX, bulk-DB, параллельный warmup; нет WebSocket |
| **Production-readiness** | ★★★★☆ | Docker, Prometheus, Grafana, health-check; нет CI/CD, нет миграций |

**Общий вердикт: 4.5/5 — зрелый проект, готовый к paper-trading.**

---

## 🟢 Что сделано хорошо

### 1. Архитектура — 13 независимых сервисов

Каждый сервис имеет единственную ответственность и чёткий интерфейс. `main.py` действует как композитный оркестратор с DI. Сервисы можно тестировать изолированно и заменять по отдельности. Разделение Online (только сбор статистики) / Offline (Walk Forward + выпуск конфига) — редкая и правильная практика.

### 2. CCXT-адаптер

`core/exchange/adapter.py` содержит Circuit Breaker, Token-bucket Rate Limiter, retry с exponential backoff, нормализацию символов, автоопределение testnet/prod, и фабрику для любой биржи. Переключение `EXCHANGE_ID=bybit` без изменения кода.

### 3. Risk Engine — исправлен критический баг

Stop-loss множитель теперь применяется к **расстоянию**, а не к сырой цене. Раньше `stop_loss * 0.8` (ultra_quiet) для LONG-позиции увеличивал риск — теперь корректно сужает расстояние. Drawdown-ключ `"max_total"` исправлен на `"total"` для соответствия `PortfolioState.total_drawdown`.

### 4. TradingView интеграция

- 4 формата алертов с автоопределением (JSON, OctoBot, Plain Text, PineConnector)
- 5 адаптеров индикаторов с PineScript-шаблонами
- Social/Sentiment сигналы (Fear & Greed, whale activity, social volume)
- Dedup + rate-limit (30-сек окно, 20 алертов/мин)
- Токен/HMAC безопасность webhook

### 5. Тесты

94 теста, 3 группы, 0 предупреждений. Покрыты: парсинг алертов, адаптеры индикаторов, social signals, Circuit Breaker, ADX/ATR/BB/CVD, 5 рыночных режимов, confidence-калибровка, Recovery Mode, Bayesian, EWMA.

### 6. Документация

Два README (EN + RU) с Mermaid-диаграммами, 7 файлов в `docs/`, `.env.example`, docstrings на английском, комментарии в коде.

---

## 🟡 Замечания (стоит исправить до prod)

### 1. `run_once()` — цикломатическая сложность E (radon)

`main.py:124` — 150+ строк в одном методе. Пайплайн линейный и читаемый, но для поддерживаемости стоит разбить на отдельные шаги:

```python
async def run_once(self):
    candles = await self._fetch_and_validate()
    if candles is None: return
    features, regimes = self._compute_features_and_regimes(candles)
    signals = self._generate_signals(features, regimes, candles)
    await self._evaluate_and_execute(signals)
    self._health_check()
```

### 2. `_detect_bounce` — цикломатическая сложность D

`services/strategy_engine/engine.py:238` — 120+ строк. LONG и SHORT ветки почти идентичны (дублирование кода). Можно вынести общую логику в `_detect_bounce_side(direction, levels, cfg)`.

### 3. Нет HTTP rate-limit на FastAPI

`api/server.py` и `api/tradingview_routes.py` не имеют middleware для ограничения запросов. DDoS на `/webhook/tradingview` пройдёт сквозь AlertManager (20/мин) но создаст нагрузку на парсер. Решение:

```python
from slowapi import Limiter
limiter = Limiter(key_func=lambda: "global")
app.state.limiter = limiter
```

### 4. WebSocket не реализован

В коде есть `self._ws_connections: Dict[str, any] = {}`, но WebSocket-подписка на тики биржи не используется. Бот живёт на 15-секундных снапшотах. Для Sweep/Bounce стратегий, которые ловят пробой/отскок уровней, это означает потенциальную задержку до 15 секунд между сигналом и входом. CCXT поддерживает `watch_ohlcv()` и `watch_ticker()` — стоит добавить.

### 5. `RECOVERY_THRESHOLD` мутируется через инстанс

```python
self.RECOVERY_THRESHOLD = config["recovery_threshold"]  # ← class-attr!
```

В `risk_engine/engine.py` — `self.RECOVERY_THRESHOLD` создаёт *instance-атрибут* (теневой), а не мутирует класс. Это работает корректно, но неочевидно. Лучше явно:

```python
self._recovery_threshold = config.get("recovery_threshold", self.RECOVERY_THRESHOLD)
```

### 6. Нет Alembic/миграций БД

`DatabaseManager.create_all()` создаёт таблицы с нуля. При изменении схемы в production потребуются миграции. Alembic — стандарт для SQLAlchemy.

### 7. Нет CI/CD

`.github/workflows/` отсутствует. GitHub Actions для авто-прогона тестов при push защитит от регрессий.

---

## 📊 Распределение кода по слоям

```
api/                 614 строк  (7.5%)    FastAPI + webhook routes
config/              256 строк  (3.1%)    YAML config registry
core/               1122 строк (13.7%)    Models, DB, Events, Exchange
services/           5220 строк (63.7%)    Business logic
main.py              382 строк  (4.7%)    Orchestrator
tests/               602 строк  (7.3%)    Unit tests
```

Код **не содержит**: TODO, FIXME, HACK, закомментированных блоков, `print()`.

---

## ✅ Чек-лист: что уже исправлено (по сравнению с предыдущим ревью)

| # | Баг | Статус |
|---|-----|--------|
| 1 | Stop-множитель к цене вместо расстояния | ✅ Исправлен |
| 2 | Мутация portfolio_state в цикле | ✅ Исправлен |
| 3 | Деление на 0 в Walk Forward Sharpe | ✅ Исправлен |
| 4 | ADX Python-циклы O(n²) | ✅ Векторизован |
| 5 | Data warmup последовательный | ✅ Параллельный с Semaphore |
| 6 | DB N отдельных merge | ✅ Bulk upsert |
| 7 | FastAPI сервер отсутствовал | ✅ Реализован |
| 9 | `datetime.utcnow()` deprecation | ✅ `datetime.now(timezone.utc)` |
| 10 | `field(default_factory=datetime.utcnow)` | ✅ `lambda:` |
| 11 | `max_total` → `total` drawdown key | ✅ Исправлен |
| 12 | Хардкод 30% в `is_stable()` | ✅ `stability_threshold` в конфиге |
| 13 | StrategyEngine class-attr мутация | ✅ `dict(self.SWEEP_CONFIG)` |
| 14 | Event Store голый `except: pass` | ✅ `logger.warning(exc_info=True)` |
| 15-22 | Мелкие замечания | ✅ Все исправлены |

---

## 🔜 Рекомендации к следующему релизу (v4.5)

| Приоритет | Задача | Часов |
|-----------|--------|-------|
| 🔴 High | CI/CD: GitHub Actions для pytest | 1 |
| 🔴 High | WebSocket подписка на тики (CCXT `watch_*`) | 3 |
| 🟡 Medium | HTTP rate-limit на FastAPI (slowapi) | 0.5 |
| 🟡 Medium | Рефакторинг `run_once()` на шаги | 2 |
| 🟡 Medium | Рефакторинг `_detect_bounce` — убрать дублирование | 1.5 |
| 🟢 Low | Alembic для миграций БД | 1 |
| 🟢 Low | `RECOVERY_THRESHOLD` → явный instance-attr | 0.25 |

---

## 📈 Итог

Проект прошёл путь от ТЗ до production-кандидата с полным покрытием тестами, двумя языками документации и мульти-биржевой архитектурой. 22 бага из предыдущего ревью исправлены. Оставшиеся замечания — это улучшения, а не блокеры. **Бот готов к paper-trading и cautious live-testing на тестнете.**
