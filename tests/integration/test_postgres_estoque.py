"""Garantias que só o PostgreSQL oferece: `SELECT ... FOR UPDATE` e as migrations do módulo.

O SQLite ignora `FOR UPDATE`, então a concorrência só é testada aqui. Estes testes commitam de
verdade (várias sessões/conexões) e limpam o que criaram.
"""

import asyncio
import os
import subprocess  # noqa: S404
import sys
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.domain.estoque.entities import Insumo, TipoMovimentacao, UnidadeMedida
from app.domain.exceptions import EstoqueInsuficiente
from app.infrastructure.persistence.estoque.models import InsumoModel, MovimentacaoEstoqueModel
from app.infrastructure.persistence.estoque.repository import SqlAlchemyEstoqueRepository

pytestmark = pytest.mark.postgres

D = Decimal
RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
async def pg_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    engine = create_async_engine(url, pool_size=15)
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def insumo_id(pg_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[int]:
    """Insumo commitado de verdade (as sessões concorrentes precisam enxergá-lo)."""
    async with pg_factory() as s:
        insumo = await SqlAlchemyEstoqueRepository(s).adicionar_insumo(
            Insumo(f"Polpa-{uuid.uuid4().hex[:8]}", UnidadeMedida.KG, D("1"))
        )
        await SqlAlchemyEstoqueRepository(s).movimentar(
            insumo.id_persistido, TipoMovimentacao.ENTRADA, D("10"), None
        )
        await s.commit()
    yield insumo.id_persistido
    async with pg_factory() as s:
        await s.execute(
            delete(MovimentacaoEstoqueModel).where(
                MovimentacaoEstoqueModel.insumo_id == insumo.id_persistido
            )
        )
        await s.execute(delete(InsumoModel).where(InsumoModel.id == insumo.id_persistido))
        await s.commit()


async def _saida(
    factory: async_sessionmaker[AsyncSession], insumo_id: int, quantidade: Decimal
) -> bool:
    """Uma 'requisição': sessão própria, lê o insumo antes (saldo em cache na sessão) e baixa."""
    async with factory() as s:
        repo = SqlAlchemyEstoqueRepository(s)
        await repo.obter_insumo(insumo_id)
        try:
            await repo.movimentar(insumo_id, TipoMovimentacao.SAIDA, quantidade, None)
        except EstoqueInsuficiente:
            await s.rollback()
            return False
        await s.commit()
        return True


async def _estado(factory: async_sessionmaker[AsyncSession], insumo_id: int) -> tuple[Decimal, int]:
    async with factory() as s:
        saldo = await s.scalar(select(InsumoModel.estoque_atual).where(InsumoModel.id == insumo_id))
        total = await s.scalar(
            select(func.count())
            .select_from(MovimentacaoEstoqueModel)
            .where(MovimentacaoEstoqueModel.insumo_id == insumo_id)
        )
    assert saldo is not None and total is not None
    return saldo, total


async def test_duas_saidas_simultaneas_nao_geram_lost_update(
    pg_factory: async_sessionmaker[AsyncSession], insumo_id: int
) -> None:
    # saldo 10; duas saídas de 6 não cabem juntas: exatamente uma passa
    resultados = await asyncio.gather(
        _saida(pg_factory, insumo_id, D("6")), _saida(pg_factory, insumo_id, D("6"))
    )
    assert sorted(resultados) == [False, True]
    saldo, movs = await _estado(pg_factory, insumo_id)
    assert saldo == D("4")
    assert movs == 2  # a entrada inicial + a única saída


async def test_muitas_saidas_simultaneas_fecham_o_saldo_exato(
    pg_factory: async_sessionmaker[AsyncSession], insumo_id: int
) -> None:
    # saldo 10, 14 saídas de 1: 10 passam, 4 falham, saldo final 0 (nunca negativo)
    resultados = await asyncio.gather(*(_saida(pg_factory, insumo_id, D("1")) for _ in range(14)))
    assert resultados.count(True) == 10
    assert resultados.count(False) == 4
    saldo, movs = await _estado(pg_factory, insumo_id)
    assert saldo == D("0")
    assert movs == 11  # entrada + 10 saídas

    # o histórico é coerente: cada saída parte do saldo em que a anterior terminou
    async with pg_factory() as s:
        linhas = (
            await s.scalars(
                select(MovimentacaoEstoqueModel)
                .where(MovimentacaoEstoqueModel.insumo_id == insumo_id)
                .order_by(MovimentacaoEstoqueModel.id)
            )
        ).all()
    for anterior, atual in zip(linhas, linhas[1:], strict=False):
        assert atual.saldo_antes == anterior.saldo_apos


async def _tabelas(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: set(inspect(c).get_table_names())))


def _alembic(*args: str, url: str) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
        text=True,
    )


async def test_migrations_0002_a_0005_aplicam_e_revertem() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    novas = {
        "categorias",
        "tamanhos",
        "produtos",
        "produto_tamanhos",
        "adicionais",
        "insumos",
        "movimentacoes_estoque",
        "itens_ficha_tecnica",
        "itens_ficha_adicional",
        "comandas",
        "itens_comanda",
        "itens_comanda_adicional",
    }
    engine = create_async_engine(url)
    try:
        _alembic("upgrade", "head", url=url)
        assert novas <= await _tabelas(engine)
        try:
            _alembic("downgrade", "0001", url=url)
            restantes = await _tabelas(engine)
            assert not (novas & restantes)
            assert {"usuarios", "audit_log"} <= restantes
        finally:
            _alembic("upgrade", "head", url=url)  # devolve o banco ao estado esperado
        assert novas <= await _tabelas(engine)
    finally:
        await engine.dispose()
