from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./calls.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id = Column(String, primary_key=True, index=True)
    duration = Column(Float, nullable=False)
    outcome = Column(Text)
    scheduled_time = Column(DateTime)
    transcript_path = Column(String)


def init_db() -> None:
    """Create database tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def save_call_summary(
    call_id: str,
    duration: float,
    outcome: str | None,
    scheduled_time: datetime | None,
    transcript_path: str | None,
) -> None:
    """Persist a call summary record."""
    session = SessionLocal()
    try:
        summary = CallSummary(
            id=call_id,
            duration=duration,
            outcome=outcome,
            scheduled_time=scheduled_time,
            transcript_path=transcript_path,
        )
        session.merge(summary)
        session.commit()
    finally:
        session.close()
