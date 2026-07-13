"""
Crypto Bot v4.4 — Database Layer
SQLite (development) / PostgreSQL (production) abstracted via SQLAlchemy.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Column, DateTime, Float, Integer, String, Text, JSON,
    PrimaryKeyConstraint, create_engine, event, Index,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════
# Table Definitions
# ═══════════════════════════════════════════════════════════════

class MarketData(Base):
    """OHLCV market data."""
    __tablename__ = "market_data"
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    open: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    high: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    low: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    close: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    volume: Mapped[float] = mapped_column(Float(precision=8), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("timestamp", "pair", "timeframe"),
        Index("idx_market_pair_tf", "pair", "timeframe"),
        Index("idx_market_ts", "timestamp"),
    )


class OIData(Base):
    """Open Interest data."""
    __tablename__ = "oi_data"
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    oi: Mapped[float] = mapped_column(Float(precision=8), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("timestamp", "pair"),
    )


class FundingData(Base):
    """Funding rate data."""
    __tablename__ = "funding_data"
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[float] = mapped_column(Float(precision=8), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("timestamp", "pair"),
    )


class TradeModel(Base):
    """Trade records."""
    __tablename__ = "trades"
    trade_id: Mapped[UUID] = mapped_column(Text, primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float(precision=8), nullable=True)
    size: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    pnl: Mapped[Optional[float]] = mapped_column(Float(precision=8), nullable=True)
    fees: Mapped[float] = mapped_column(Float(precision=8), default=0.0)
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(precision=2), default=0.0)


class ConfigVersion(Base):
    """Config version registry."""
    __tablename__ = "config_versions"
    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)


class ExperimentModel(Base):
    """Experiment records."""
    __tablename__ = "experiments"
    experiment_id: Mapped[UUID] = mapped_column(Text, primary_key=True, default=uuid4)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    config_version: Mapped[str] = mapped_column(String(20), nullable=False)
    data_period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    data_period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict)


class EventModel(Base):
    """Event sourcing store."""
    __tablename__ = "events"
    event_id: Mapped[UUID] = mapped_column(Text, primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class ExecutionRecordModel(Base):
    """Quality of execution records."""
    __tablename__ = "execution_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_price: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    actual_price: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    slippage: Mapped[float] = mapped_column(Float(precision=8), nullable=False)
    latency: Mapped[float] = mapped_column(Float, nullable=False)
    partial_fill: Mapped[bool] = mapped_column(default=False)
    cancelled: Mapped[bool] = mapped_column(default=False)


# ═══════════════════════════════════════════════════════════════
# Database Manager
# ═══════════════════════════════════════════════════════════════

class DatabaseManager:
    """Manages database connections and session lifecycle."""

    def __init__(self, url: str = "sqlite:///crypto_bot_v4.db"):
        self.url = url
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None

    def connect(self):
        """Initialize engine and session factory."""
        self.engine = create_engine(
            self.url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if "sqlite" in self.url else {},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

        # Enable WAL mode for SQLite for better concurrency
        if "sqlite" in self.url:
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.close()

    def create_all(self):
        """Create all tables."""
        if self.engine is None:
            self.connect()
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        if self.SessionLocal is None:
            self.connect()
        return self.SessionLocal()

    def close(self):
        """Close the engine."""
        if self.engine:
            self.engine.dispose()

    def insert_market_data_batch(self, records: list[dict], session: Optional[Session] = None):
        """Bulk-insert market data records."""
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True
        try:
            for rec in records:
                md = MarketData(**rec)
                session.merge(md)  # merge handles upsert
            session.commit()
        finally:
            if close_session:
                session.close()

    def query_market_data(
        self,
        pair: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        session: Optional[Session] = None,
    ) -> list[dict]:
        """Query market data for a pair/timeframe range."""
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True
        try:
            q = session.query(MarketData).filter(
                MarketData.pair == pair,
                MarketData.timeframe == timeframe,
                MarketData.timestamp >= start,
            )
            if end:
                q = q.filter(MarketData.timestamp <= end)
            q = q.order_by(MarketData.timestamp.asc())
            rows = q.all()
            return [
                {
                    "timestamp": r.timestamp,
                    "pair": r.pair,
                    "timeframe": r.timeframe,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in rows
            ]
        finally:
            if close_session:
                session.close()
