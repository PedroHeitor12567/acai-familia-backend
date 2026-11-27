"""Concorrência do fechamento de comandas: só o PostgreSQL honra `SELECT ... FOR UPDATE`.

Cada "requisição" usa a própria sessão (conexão), como em produção. Os dados são commitados de
verdade (as sessões concorrentes precisam enxergá-los) e removidos no fim.
"""

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.application.comandas.use_cases.itens import AdicionarItem
from app.bootstrap.container import build_uow
from app.domain.comandas.entities import StatusComanda
from app.domain.comandas.regras import total_comanda
from app.domain.exceptions import EstoqueInsuficienteNoFechamento, OperacaoNaoPermitida
from app.infrastructure.persistence.estoque.models import InsumoModel
from tests.pg_cenario import Cenario, Factory, _cenario, _resultado

pytestmark = pytest.mark.postgres

D = Decimal


@pytest.fixture
async def cenario_folgado(pg_factory: Factory) -> AsyncIterator[Cenario]:
    """3 insumos com 100 de saldo cada; o produto "todos" consome 1 de cada."""
    async for c in _cenario(pg_factory, ["100", "100", "100"]):
        yield c


async def test_dois_fechamentos_simultaneos_da_mesma_comanda(cenario_folgado: Cenario) -> None:
    c = cenario_folgado
    cid = await c.comanda_com_item(quantidade=5)

    # Um insumo travado "segura" os fechamentos até todos já terem lido a comanda como aberta:
    # sem o lock da comanda, os três baixariam o estoque. Com ele, só o primeiro chega ao insumo.
    async with c.factory() as segurando:
        await segurando.scalar(
            select(InsumoModel.id).where(InsumoModel.id == c.insumos[0]).with_for_update()
        )
        tarefas = [asyncio.create_task(_resultado(c.fechar(cid))) for _ in range(3)]
        await asyncio.sleep(0.5)
        await segurando.rollback()
    resultados = await asyncio.gather(*tarefas)

    erros = [r for r in resultados if isinstance(r, Exception)]
    assert len(erros) == 2  # um fecha; os outros veem "fechada" e recebem 409
    assert all(
        isinstance(e, OperacaoNaoPermitida) and e.motivo == "comanda_nao_aberta" for e in erros
    )
    assert await c.status(cid) is StatusComanda.FECHADA
    for insumo_id in c.insumos:
        assert await c.saldo(insumo_id) == D("95")  # baixado UMA vez (5), não duas
        assert await c.saidas(insumo_id) == 1


async def test_duas_comandas_disputando_o_mesmo_insumo_com_saldo_para_uma(
    pg_factory: Factory,
) -> None:
    async for c in _cenario(pg_factory, ["1", "50", "50"], {"todos": [0, 1, 2]}):
        primeira, segunda = await c.comanda_com_item(), await c.comanda_com_item()

        resultados = await asyncio.gather(
            _resultado(c.fechar(primeira)), _resultado(c.fechar(segunda))
        )

        erros = [r for r in resultados if isinstance(r, Exception)]
        assert len(erros) == 1 and isinstance(erros[0], EstoqueInsuficienteNoFechamento)
        assert erros[0].insumo_id == c.insumos[0]
        assert sorted([await c.status(primeira), await c.status(segunda)]) == [
            StatusComanda.ABERTA,
            StatusComanda.FECHADA,
        ]
        assert await c.saldo(c.insumos[0]) == D("0")  # nunca negativo
        # a que perdeu desfez também as baixas dos outros insumos (rollback total)
        assert await c.saldo(c.insumos[1]) == D("49") and await c.saldo(c.insumos[2]) == D("49")


async def test_ultimo_insumo_sem_saldo_desfaz_as_baixas_anteriores(pg_factory: Factory) -> None:
    async for c in _cenario(pg_factory, ["10", "10", "0"], {"todos": [0, 1, 2]}):
        cid = await c.comanda_com_item(quantidade=2)

        with pytest.raises(EstoqueInsuficienteNoFechamento) as erro:
            await c.fechar(cid)

        assert erro.value.insumo_id == c.insumos[2]
        assert await c.saldo(c.insumos[0]) == D("10") and await c.saldo(c.insumos[1]) == D("10")
        assert [await c.saidas(i) for i in c.insumos] == [0, 0, 0]  # nenhuma movimentação
        assert await c.status(cid) is StatusComanda.ABERTA
        async with c.factory() as s:
            comanda = await build_uow(s).comandas.obter(cid)
        assert comanda is not None and comanda.total_fechado is None and comanda.fechada_em is None


async def test_adicionar_item_enquanto_outro_processo_fecha(pg_factory: Factory) -> None:
    async for c in _cenario(pg_factory, ["1000", "1000", "1000"], {"todos": [0, 1, 2]}):
        for _ in range(8):
            cid = await c.comanda_com_item()
            antes = [await c.saldo(i) for i in c.insumos]

            async def lancar(cid: int = cid, c: Cenario = c) -> None:
                async with c.factory() as s:
                    await AdicionarItem(build_uow(s)).executar(
                        c.ator, cid, c.produtos["todos"], c.tamanho_id, 3
                    )

            r_fechar, r_lancar = await asyncio.gather(
                _resultado(c.fechar(cid)), _resultado(lancar())
            )

            assert r_fechar is None  # o fechamento nunca perde a corrida
            async with c.factory() as s:
                comanda = await build_uow(s).comandas.obter(cid)
            assert comanda is not None and comanda.status is StatusComanda.FECHADA
            if r_lancar is None:  # o item entrou antes do lock do fechamento: foi contado
                assert len(comanda.itens) == 2 and comanda.total_fechado == D("40.00")
                baixado = D("4")
            else:  # entrou depois: recusado, e o fechamento não o contou
                assert isinstance(r_lancar, OperacaoNaoPermitida)
                assert r_lancar.motivo == "comanda_nao_aberta"
                assert len(comanda.itens) == 1 and comanda.total_fechado == D("10.00")
                baixado = D("1")
            # o snapshot e a baixa batem sempre com os itens que realmente ficaram na comanda
            assert comanda.total_fechado == total_comanda(comanda.itens)
            assert [antes[i] - await c.saldo(insumo) for i, insumo in enumerate(c.insumos)] == [
                baixado
            ] * 3


async def test_fechamentos_cruzados_em_varios_insumos_nao_dao_deadlock(
    pg_factory: Factory,
) -> None:
    # produtos que usam combinações diferentes dos mesmos insumos, fechados ao mesmo tempo
    fichas = {"ab": [0, 1], "bc": [1, 2], "ca": [2, 0], "ba": [1, 0], "abc": [0, 1, 2]}
    async for c in _cenario(pg_factory, ["500", "500", "500"], fichas):
        nomes = list(fichas) * 4  # 20 fechamentos concorrentes
        comandas = [await c.comanda_com_item(nome) for nome in nomes]

        resultados = await asyncio.wait_for(
            asyncio.gather(*(_resultado(c.fechar(cid)) for cid in comandas)), timeout=60
        )

        assert [r for r in resultados if r is not None] == []  # nenhum deadlock, todos fecharam
        esperado = [D("500")] * 3
        for nome in nomes:
            for pos in fichas[nome]:
                esperado[pos] -= 1
        assert [await c.saldo(i) for i in c.insumos] == esperado
        # uma saída por insumo de cada comanda (a baixa é agregada por insumo)
        assert sum([await c.saidas(i) for i in c.insumos]) == sum(len(fichas[n]) for n in nomes)
