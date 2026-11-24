from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def agora() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass
