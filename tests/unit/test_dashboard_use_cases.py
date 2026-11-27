from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.dashboard.contas import ObterPosicaoContas
from app.application.dashboard.estoque_critico import ObterEstoqueCritico
from app.application.dashboard.fluxo_caixa import ObterFluxoCaixa
from app.application.dashboard.mais_vendidos import ObterMaisVendidos
from app.application.dashboard.resumo_vendas import ObterResumoVendas
from app.application.dashboard.serie_vendas import ObterSerieVendas
from app.application.dashboard.vendas_por_forma import ObterVendasPorForma
from app.application.dashboard.visao_geral import ObterVisaoGeral
from app.domain.dashboard.modelos import (
    CaixaAberto,
    FatoCaixa,
    InsumoCritico,
    LinhaProduto,
    NivelEstoque,
    OrdenarPor,
    PosicaoConta,
    TotaisVendas,
    Vencimento,
    VendaDia,
    VendaForma,
)
from app.domain.dashboard.periodo import Agrupamento, Periodo
from app.domain.exceptions import PeriodoInvalido, PermissaoNegada
from app.domain.financeiro.entities import TipoLancamento
from app.domain.usuarios.entities import Papel, Usuario

D = Decimal
HOJE = date(2026, 11, 27)
ZERO = D("0.00")


def _ator(papel: Papel) -> Usuario:
    return Usuario(nome="X", email="x@acai.com", senha_hash="x", papel=papel, id=1)


def _posicao(tipo: TipoLancamento, **campos: object) -> PosicaoConta:
    base: dict[str, object] = {
        "total_pendente": ZERO,
        "qtd_pendente": 0,
        "total_atrasado": ZERO,
        "qtd_atrasado": 0,
        "vence_hoje_valor": ZERO,
        "vence_hoje_qtd": 0,
        "vence_em_7_dias_valor": ZERO,
        "vence_em_7_dias_qtd": 0,
    }
    return PosicaoConta(tipo, **{**base, **campos})  # type: ignore[arg-type]


class FakeQueries:
    """Guarda o que foi pedido e devolve respostas prontas."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[str, tuple[object, ...]]] = []
        self.atual = TotaisVendas(D("200.00"), 4, 9, 2)
        self.anterior = TotaisVendas(D("100.00"), 5)
        self.dias: list[VendaDia] = []
        self.ranking: list[LinhaProduto] = []
        self.receita_total = ZERO
        self.formas: list[VendaForma] = []
        self.insumos: list[InsumoCritico] = []
        self.fatos: list[FatoCaixa] = []
        self.caixa: CaixaAberto | None = None
        self.pagar = _posicao(TipoLancamento.PAGAR)
        self.receber = _posicao(TipoLancamento.RECEBER)

    async def comparativo_vendas(
        self, atual: Periodo, anterior: Periodo
    ) -> tuple[TotaisVendas, TotaisVendas]:
        self.chamadas.append(("comparativo", (atual, anterior)))
        return self.atual, self.anterior

    async def vendas_por_dia(self, periodo: Periodo) -> list[VendaDia]:
        self.chamadas.append(("dia", (periodo,)))
        return self.dias

    async def mais_vendidos(
        self, periodo: Periodo, ordenar_por: OrdenarPor, limite: int
    ) -> tuple[list[LinhaProduto], Decimal]:
        self.chamadas.append(("ranking", (periodo, ordenar_por, limite)))
        return self.ranking, self.receita_total

    async def vendas_por_forma(self, periodo: Periodo) -> list[VendaForma]:
        return self.formas

    async def vendas_por_hora(self, periodo: Periodo) -> list[object]:
        return []

    async def insumos_criticos(self) -> list[InsumoCritico]:
        return self.insumos

    async def fatos_fluxo_caixa(self, periodo: Periodo, incluir_projecao: bool) -> list[FatoCaixa]:
        self.chamadas.append(("fluxo", (periodo, incluir_projecao)))
        return self.fatos

    async def posicao_contas(self, hoje: date) -> dict[TipoLancamento, PosicaoConta]:
        return {TipoLancamento.PAGAR: self.pagar, TipoLancamento.RECEBER: self.receber}

    async def proximos_vencimentos(self, hoje: date, limite: int) -> list[Vencimento]:
        self.chamadas.append(("proximos", (limite,)))
        return []

    async def comandas_abertas(self) -> int:
        return 3

    async def caixa_aberto(self) -> CaixaAberto | None:
        return self.caixa


@pytest.fixture
def q() -> FakeQueries:
    return FakeQueries()


GESTORES = [Papel.ADMIN, Papel.GERENTE]
SEM_ACESSO = [Papel.CAIXA, Papel.ATENDENTE]


@pytest.mark.parametrize("papel", SEM_ACESSO)
async def test_so_gestor_consulta_o_dashboard(q: FakeQueries, papel: Papel) -> None:
    ator = _ator(papel)
    casos = [
        ObterResumoVendas(q).executar(ator, None, None, HOJE),
        ObterSerieVendas(q).executar(ator, None, None, HOJE, Agrupamento.DIA),
        ObterMaisVendidos(q).executar(ator, None, None, HOJE, 10, OrdenarPor.QUANTIDADE),
        ObterVendasPorForma(q).executar(ator, None, None, HOJE),
        ObterEstoqueCritico(q).executar(ator, None, 50, 0),
        ObterFluxoCaixa(q).executar(ator, None, None, HOJE, Agrupamento.DIA, False),
        ObterPosicaoContas(q).executar(ator, HOJE),
        ObterVisaoGeral(q).executar(ator, HOJE),
    ]
    for caso in casos:
        with pytest.raises(PermissaoNegada):
            await caso
    assert q.chamadas == []  # negado antes de consultar


async def test_resumo_calcula_ticket_e_variacao_contra_o_periodo_anterior(q: FakeQueries) -> None:
    resumo = await ObterResumoVendas(q).executar(
        _ator(Papel.GERENTE), date(2026, 11, 1), date(2026, 11, 27), HOJE
    )
    assert resumo.periodo_anterior == Periodo(date(2026, 10, 5), date(2026, 10, 31))
    assert q.chamadas == [("comparativo", (resumo.periodo, resumo.periodo_anterior))]
    assert (resumo.ticket_medio, resumo.ticket_medio_anterior) == (D("50.00"), D("20.00"))
    assert resumo.variacao_pct.faturamento == D("100.0")
    assert resumo.variacao_pct.qtd_comandas == D("-20.0")
    assert resumo.variacao_pct.ticket_medio == D("150.0")


async def test_resumo_sem_periodo_anterior_tem_variacao_nula(q: FakeQueries) -> None:
    q.anterior = TotaisVendas(ZERO, 0)
    resumo = await ObterResumoVendas(q).executar(_ator(Papel.ADMIN), None, None, HOJE)
    assert resumo.ticket_medio_anterior == ZERO
    assert (
        resumo.variacao_pct.faturamento,
        resumo.variacao_pct.qtd_comandas,
        resumo.variacao_pct.ticket_medio,
    ) == (None, None, None)


async def test_periodo_invalido_nao_chega_ao_banco(q: FakeQueries) -> None:
    with pytest.raises(PeriodoInvalido):
        await ObterResumoVendas(q).executar(
            _ator(Papel.ADMIN), HOJE, HOJE - timedelta(days=1), HOJE
        )
    with pytest.raises(PeriodoInvalido):
        await ObterSerieVendas(q).executar(
            _ator(Papel.ADMIN), HOJE - timedelta(days=120), HOJE, HOJE, Agrupamento.DIA
        )
    assert q.chamadas == []


async def test_serie_preenche_zeros_e_soma_igual_ao_total(q: FakeQueries) -> None:
    q.dias = [VendaDia(date(2026, 11, 26), D("30.00"), 2), VendaDia(HOJE, D("12.50"), 1)]
    periodo, serie = await ObterSerieVendas(q).executar(
        _ator(Papel.ADMIN), date(2026, 11, 24), HOJE, HOJE, Agrupamento.DIA
    )
    assert periodo.dias == len(serie) == 4
    assert sum(p.faturamento for p in serie) == D("42.50")


async def test_mais_vendidos_calcula_participacao(q: FakeQueries) -> None:
    q.ranking = [
        LinhaProduto(1, "Açaí", 3, D("60.00")),
        LinhaProduto(2, "Suco", 1, D("20.00")),
    ]
    q.receita_total = D("100.00")  # há outros produtos fora do top
    _, itens = await ObterMaisVendidos(q).executar(
        _ator(Papel.ADMIN), None, None, HOJE, 2, OrdenarPor.RECEITA
    )
    assert [i.participacao_pct for i in itens] == [D("60.0"), D("20.0")]


async def test_estoque_critico_pagina_em_memoria_e_conta_tudo(q: FakeQueries) -> None:
    q.insumos = [
        InsumoCritico(1, "A", "kg", D("0.000"), D("1.000")),
        InsumoCritico(2, "B", "kg", D("0.500"), D("1.000")),
        InsumoCritico(3, "C", "kg", D("0.600"), D("1.000")),
        InsumoCritico(4, "D", "kg", D("9.000"), D("1.000")),  # não é crítico
    ]
    caso = ObterEstoqueCritico(q)
    pagina = await caso.executar(_ator(Papel.ADMIN), None, 2, 0)
    assert (pagina.total_zerados, pagina.total_criticos, pagina.total) == (1, 2, 3)
    assert [i.nome for i in pagina.itens] == ["A", "B"]

    so_criticos = await caso.executar(_ator(Papel.ADMIN), NivelEstoque.CRITICO, 50, 0)
    assert so_criticos.total == 2
    assert (so_criticos.total_zerados, so_criticos.total_criticos) == (1, 2)  # contadores gerais

    alem = await caso.executar(_ator(Papel.ADMIN), None, 2, 10)
    assert alem.itens == [] and (alem.total_zerados, alem.total_criticos) == (1, 2)


async def test_fluxo_so_aceita_periodo_futuro_com_projecao(q: FakeQueries) -> None:
    caso = ObterFluxoCaixa(q)
    futuro = HOJE + timedelta(days=10)
    with pytest.raises(PeriodoInvalido):
        await caso.executar(_ator(Papel.ADMIN), HOJE, futuro, HOJE, Agrupamento.DIA, False)
    fluxo = await caso.executar(_ator(Papel.ADMIN), HOJE, futuro, HOJE, Agrupamento.DIA, True)
    assert fluxo.projecao is not None and len(fluxo.projecao) == 11
    assert q.chamadas[-1][1][1] is True


async def test_contas_busca_no_maximo_10_proximos(q: FakeQueries) -> None:
    posicao = await ObterPosicaoContas(q).executar(_ator(Papel.ADMIN), HOJE)
    assert posicao.hoje == HOJE
    assert q.chamadas == [("proximos", (10,))]


async def test_visao_geral_compara_com_o_mesmo_dia_da_semana_anterior(q: FakeQueries) -> None:
    q.caixa = CaixaAberto(7, D("100.00"), D("50.00"), D("20.00"), D("30.00"))
    q.insumos = [
        InsumoCritico(1, "A", "kg", D("0"), D("1")),
        InsumoCritico(2, "B", "kg", D("0.5"), D("1")),
    ]
    q.pagar = _posicao(
        TipoLancamento.PAGAR,
        total_atrasado=D("80.00"),
        qtd_atrasado=2,
        vence_hoje_valor=D("15.00"),
    )
    v = await ObterVisaoGeral(q).executar(_ator(Papel.GERENTE), HOJE)

    atual, anterior = q.chamadas[0][1]
    assert atual == Periodo(HOJE, HOJE)
    assert anterior == Periodo(HOJE - timedelta(days=7), HOJE - timedelta(days=7))
    assert v.vendas_hoje.comparado_com == date(2026, 11, 20)
    assert (v.vendas_hoje.faturamento, v.vendas_hoje.ticket_medio) == (D("200.00"), D("50.00"))
    assert v.comandas_abertas == 3
    assert (v.caixa.aberto, v.caixa.sessao_id, v.caixa.saldo_dinheiro) == (True, 7, D("140.00"))
    assert (v.estoque.total_zerados, v.estoque.total_criticos) == (1, 1)
    assert (v.contas.qtd_atrasadas_pagar, v.contas.valor_atrasado_pagar) == (2, D("80.00"))
    assert v.contas.vence_hoje_pagar == D("15.00")


async def test_visao_geral_com_caixa_fechado_nao_inventa_saldo(q: FakeQueries) -> None:
    v = await ObterVisaoGeral(q).executar(_ator(Papel.ADMIN), HOJE)
    assert (v.caixa.aberto, v.caixa.sessao_id, v.caixa.saldo_dinheiro) == (False, None, None)
