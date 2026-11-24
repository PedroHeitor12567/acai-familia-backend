import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.infrastructure.persistence.registry import Base

target_metadata = Base.metadata
url = get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _executar(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.run_sync(_executar)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
