import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.application.caixa.use_cases.movimentos import RegistrarMovimento
from app.application.caixa.use_cases.sessoes import AbrirCaixa, FecharCaixa
from app.application.comandas.use_cases.fechamento import FecharComanda
from app.bootstrap.container import build_uow
from app.domain.caixa.entities import (
    FormaPagamento,
    PagamentoPedido,
    StatusSessao,
    TipoMovimento,
)
from app.domain.comandas.entities import StatusComanda
from app.domain.exceptions import EstoqueInsuficienteNoFechamento, OperacaoNaoPermitida
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.caixa.models import (
    MovimentoCaixaModel,
    PagamentoModel,
    SessaoCaixaModel,
)
from app.infrastructure.persistence.usuarios.models import UsuarioModel
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository
from tests.integration.test_postgres_estoque import _alembic, _tabelas
from tests.pg_cenario import Cenario, Factory, _cenario, _resultado

pytestmark = pytest.mark.postgres

D = Decimal


@pytest.fixture
async def cenario_folgado(pg_factory: Factory) -> AsyncIterator[Cenario]:
    async for c in _cenario(pg_factory, ["1000", "1000", "1000"]):
        yield c


@pytest.fixture
async def operador(pg_factory: Factory) -> AsyncIterator[Usuario]:
    async with pg_factory() as s:
        ator = await SqlAlchemyUsuarioRepository(s).adicionar(
            Usuario("Caixa PG", f"caixa-{uuid.uuid4().hex[:8]}@acai.com", "x", Papel.CAIXA)
        )
        await s.commit()
    try:
        yield ator
    finally:
        async with pg_factory() as s:
            await s.execute(
                delete(MovimentoCaixaModel).where(MovimentoCaixaModel.criado_por_id == ator.id)
            )
            await s.execute(
                delete(SessaoCaixaModel).where(SessaoCaixaModel.aberta_por_id == ator.id)
            )
            await s.execute(delete(AuditLogModel).where(AuditLogModel.usuario_id == ator.id))
            await s.execute(delete(UsuarioModel).where(UsuarioModel.id == ator.id))
            await s.commit()


async def _com_sessao_travada(
    c: Cenario, sessao_id: int, *operacoes: Callable[[], Awaitable[None]]
) -> list[Exception | None]:
    async with c.factory() as segurando:
        await segurando.scalar(
            select(SessaoCaixaModel.id).where(SessaoCaixaModel.id == sessao_id).with_for_update()
        )
        tarefas = [asyncio.create_task(_resultado(op())) for op in operacoes]
        await asyncio.sleep(0.5)
        await segurando.rollback()
    return list(await asyncio.gather(*tarefas))


async def _abrir(c: Cenario) -> int:
    async with c.factory() as s:
        return (await AbrirCaixa(build_uow(s)).executar(c.ator, D("0.00"))).id_persistido


async def test_duas_aberturas_simultaneas_uma_vence_e_so_uma_fica_aberta(
    pg_factory: Factory, operador: Usuario
) -> None:
    async def abrir() -> None:
        async with pg_factory() as s:
            await AbrirCaixa(build_uow(s)).executar(operador, D("50.00"))

    resultados = await asyncio.gather(_resultado(abrir()), _resultado(abrir()))

    erros = [r for r in resultados if isinstance(r, Exception)]
    assert len(erros) == 1
    assert isinstance(erros[0], OperacaoNaoPermitida) and erros[0].motivo == "caixa_ja_aberto"
    async with pg_factory() as s:
        abertas = await s.scalar(
            select(func.count())
            .select_from(SessaoCaixaModel)
            .where(
                SessaoCaixaModel.aberta_por_id == operador.id, SessaoCaixaModel.status == "aberta"
            )
        )
    assert abertas == 1


async def test_fechar_comanda_concorrente_com_fechar_caixa_nunca_deixa_pagamento_em_sessao_fechada(
    cenario_folgado: Cenario,
) -> None:
    c = cenario_folgado
    sessao_id = c.sessao_id
    for rodada in range(8):
        cid = await c.comanda_com_item()

        async def fechar_comanda(cid: int = cid) -> None:
            async with c.factory() as s:
                await FecharComanda(build_uow(s)).executar(
                    c.ator, cid, [PagamentoPedido(FormaPagamento.DINHEIRO, D("10.00"))]
                )

        async def fechar_caixa(sessao_id: int = sessao_id) -> None:
            async with c.factory() as s:
                await FecharCaixa(build_uow(s)).executar(c.ator, sessao_id, D("10.00"), "contagem")

        r_comanda, r_caixa = await _com_sessao_travada(c, sessao_id, fechar_comanda, fechar_caixa)

        async with c.factory() as s:
            sessao = await build_uow(s).caixa.obter_sessao(sessao_id)
        assert sessao is not None and sessao.status is StatusSessao.FECHADA
        if r_comanda is None:
            assert await c.status(cid) is StatusComanda.FECHADA
            assert await c.pagamentos(cid) == 1
            assert sessao.valor_esperado == D("10.00")
            assert r_caixa is None
        else:
            assert isinstance(r_comanda, OperacaoNaoPermitida)
            assert r_comanda.motivo == "caixa_fechado"
            assert await c.status(cid) is StatusComanda.ABERTA
            assert await c.pagamentos(cid) == 0
            assert sessao.valor_esperado == D("0.00")
        async with c.factory() as s:
            tardios = await s.scalar(
                select(func.count())
                .select_from(PagamentoModel)
                .join(SessaoCaixaModel, SessaoCaixaModel.id == PagamentoModel.sessao_id)
                .where(
                    PagamentoModel.sessao_id == sessao_id,
                    PagamentoModel.criado_em > SessaoCaixaModel.fechada_em,
                )
            )
        assert tardios == 0
        if rodada < 7:
            sessao_id = await _abrir(c)


async def test_dois_fechamentos_da_mesma_comanda_gravam_um_pagamento_e_uma_baixa(
    cenario_folgado: Cenario,
) -> None:
    c = cenario_folgado
    cid = await c.comanda_com_item(quantidade=5)

    resultados = await _com_sessao_travada(
        c, c.sessao_id, *[lambda: c.fechar(cid) for _ in range(3)]
    )

    erros = [r for r in resultados if r is not None]
    assert len(erros) == 2 and all(
        isinstance(e, OperacaoNaoPermitida) and e.motivo == "comanda_nao_aberta" for e in erros
    )
    assert await c.pagamentos(cid) == 1
    for insumo_id in c.insumos:
        assert await c.saldo(insumo_id) == D("995")
        assert await c.saidas(insumo_id) == 1


async def test_falta_de_estoque_depois_dos_pagamentos_montados_faz_rollback_total(
    pg_factory: Factory,
) -> None:
    async for c in _cenario(pg_factory, ["10", "10", "0"]):
        cid = await c.comanda_com_item(quantidade=2)

        with pytest.raises(EstoqueInsuficienteNoFechamento):
            await c.fechar(cid)

        assert await c.pagamentos(cid) == 0
        assert [await c.saidas(i) for i in c.insumos] == [0, 0, 0]
        assert await c.status(cid) is StatusComanda.ABERTA
        assert await c.saldo(c.insumos[0]) == D("10")


async def test_duas_sangrias_concorrentes_que_excedem_o_saldo_so_uma_passa(
    cenario_folgado: Cenario,
) -> None:
    c = cenario_folgado
    async with c.factory() as s:
        await RegistrarMovimento(build_uow(s)).executar(
            c.ator, c.sessao_id, TipoMovimento.SUPRIMENTO, D("100.00"), "reforço de troco"
        )

    async def sangria() -> None:
        async with c.factory() as s:
            await RegistrarMovimento(build_uow(s)).executar(
                c.ator, c.sessao_id, TipoMovimento.SANGRIA, D("60.00"), "pagamento de fornecedor"
            )

    resultados = await _com_sessao_travada(c, c.sessao_id, sangria, sangria)

    erros = [r for r in resultados if r is not None]
    assert len(erros) == 1
    assert isinstance(erros[0], OperacaoNaoPermitida)
    assert erros[0].motivo == "saldo_caixa_insuficiente"
    async with c.factory() as s:
        detalhe_saldo = await s.scalar(
            select(func.coalesce(func.sum(MovimentoCaixaModel.valor), 0)).where(
                MovimentoCaixaModel.sessao_id == c.sessao_id,
                MovimentoCaixaModel.tipo == "sangria",
            )
        )
    assert detalhe_saldo == D("60.00")


async def test_fechamentos_paralelos_com_insumos_em_comum_nao_dao_deadlock(
    pg_factory: Factory,
) -> None:
    fichas = {"ab": [0, 1], "bc": [1, 2], "ca": [2, 0], "ba": [1, 0], "abc": [0, 1, 2]}
    async for c in _cenario(pg_factory, ["500", "500", "500"], fichas):
        nomes = list(fichas) * 4
        comandas = [await c.comanda_com_item(nome) for nome in nomes]

        resultados = await asyncio.wait_for(
            asyncio.gather(*(_resultado(c.fechar(cid)) for cid in comandas)), timeout=60
        )

        assert [r for r in resultados if r is not None] == []
        assert sum([await c.pagamentos(cid) for cid in comandas]) == len(comandas)


async def test_migrations_0006_a_0008_aplicam_e_revertem() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    novas = {
        "caixa_sessoes",
        "caixa_movimentos",
        "pagamentos",
        "categorias_financeiras",
        "lancamentos",
    }
    engine = create_async_engine(url)
    try:
        _alembic("upgrade", "head", url=url)
        assert novas <= await _tabelas(engine)
        try:
            _alembic("downgrade", "0005", url=url)  # desfaz 0009 (índices), 0008, 0007 e 0006
            assert not (novas & await _tabelas(engine))
            assert "comandas" in await _tabelas(engine)
        finally:
            _alembic("upgrade", "head", url=url)
        assert novas <= await _tabelas(engine)
    finally:
        await engine.dispose()
