"""Dashboard: 100% leitura, restrito a admin e gerente. Nada aqui grava dado ou auditoria."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.domain.dashboard.calculos import ZERO
from app.domain.dashboard.modelos import NivelEstoque, OrdenarPor
from app.domain.dashboard.periodo import Agrupamento
from app.interfaces.http.deps import (
    GestorDep,
    HojeDep,
    ObterEstoqueCriticoDep,
    ObterFluxoCaixaDep,
    ObterMaisVendidosDep,
    ObterPosicaoContasDep,
    ObterResumoVendasDep,
    ObterSerieVendasDep,
    ObterVendasPorFormaDep,
    ObterVendasPorHoraDep,
    ObterVisaoGeralDep,
)
from app.interfaces.http.schemas.dashboard import (
    ContasOut,
    FluxoCaixaOut,
    MaisVendidosOut,
    PaginaEstoqueCriticoOut,
    PeriodoOut,
    PontoSerieOut,
    ProdutoVendidoOut,
    ResumoVendasOut,
    SerieVendasOut,
    VendaFormaOut,
    VendaHoraOut,
    VendasPorFormaOut,
    VendasPorHoraOut,
    VisaoGeralOut,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

De = Annotated[
    date | None,
    Query(description="Início inclusivo, no fuso da loja (padrão: 29 dias antes de `ate`)"),
]
Ate = Annotated[date | None, Query(description="Fim inclusivo, no fuso da loja (padrão: hoje)")]


@router.get("/visao-geral", response_model=VisaoGeralOut)
async def visao_geral(ator: GestorDep, caso: ObterVisaoGeralDep, hoje: HojeDep) -> VisaoGeralOut:
    return VisaoGeralOut.de_visao(await caso.executar(ator, hoje))


@router.get("/vendas/resumo", response_model=ResumoVendasOut)
async def resumo_vendas(
    ator: GestorDep, caso: ObterResumoVendasDep, hoje: HojeDep, de: De = None, ate: Ate = None
) -> ResumoVendasOut:
    return ResumoVendasOut.de_resumo(await caso.executar(ator, de, ate, hoje))


@router.get("/vendas/serie", response_model=SerieVendasOut)
async def serie_vendas(
    ator: GestorDep,
    caso: ObterSerieVendasDep,
    hoje: HojeDep,
    de: De = None,
    ate: Ate = None,
    agrupamento: Agrupamento = Agrupamento.DIA,
) -> SerieVendasOut:
    periodo, pontos = await caso.executar(ator, de, ate, hoje, agrupamento)
    return SerieVendasOut(
        periodo=PeriodoOut.de_periodo(periodo),
        agrupamento=agrupamento,
        pontos=[PontoSerieOut(**vars(p)) for p in pontos],
        total_faturamento=sum((p.faturamento for p in pontos), start=ZERO),
        total_comandas=sum(p.qtd_comandas for p in pontos),
    )


@router.get("/vendas/mais-vendidos", response_model=MaisVendidosOut)
async def mais_vendidos(
    ator: GestorDep,
    caso: ObterMaisVendidosDep,
    hoje: HojeDep,
    de: De = None,
    ate: Ate = None,
    limite: Annotated[int, Query(ge=1, le=50)] = 10,
    ordenar_por: OrdenarPor = OrdenarPor.QUANTIDADE,
) -> MaisVendidosOut:
    periodo, itens = await caso.executar(ator, de, ate, hoje, limite, ordenar_por)
    return MaisVendidosOut(
        periodo=PeriodoOut.de_periodo(periodo),
        itens=[ProdutoVendidoOut(**vars(i)) for i in itens],
    )


@router.get("/vendas/por-forma-pagamento", response_model=VendasPorFormaOut)
async def vendas_por_forma_pagamento(
    ator: GestorDep, caso: ObterVendasPorFormaDep, hoje: HojeDep, de: De = None, ate: Ate = None
) -> VendasPorFormaOut:
    periodo, formas = await caso.executar(ator, de, ate, hoje)
    return VendasPorFormaOut(
        periodo=PeriodoOut.de_periodo(periodo),
        total=sum((f.valor for f in formas), start=ZERO),
        formas=[VendaFormaOut(**vars(f)) for f in formas],
    )


@router.get("/vendas/por-hora", response_model=VendasPorHoraOut)
async def vendas_por_hora(
    ator: GestorDep, caso: ObterVendasPorHoraDep, hoje: HojeDep, de: De = None, ate: Ate = None
) -> VendasPorHoraOut:
    periodo, horas = await caso.executar(ator, de, ate, hoje)
    return VendasPorHoraOut(
        periodo=PeriodoOut.de_periodo(periodo), horas=[VendaHoraOut(**vars(h)) for h in horas]
    )


@router.get("/estoque/critico", response_model=PaginaEstoqueCriticoOut)
async def estoque_critico(
    ator: GestorDep,
    caso: ObterEstoqueCriticoDep,
    nivel: NivelEstoque | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginaEstoqueCriticoOut:
    return PaginaEstoqueCriticoOut.de_pagina(await caso.executar(ator, nivel, limit, offset))


@router.get("/financeiro/fluxo-caixa", response_model=FluxoCaixaOut)
async def fluxo_caixa(
    ator: GestorDep,
    caso: ObterFluxoCaixaDep,
    hoje: HojeDep,
    de: De = None,
    ate: Ate = None,
    agrupamento: Agrupamento = Agrupamento.DIA,
    incluir_projecao: Annotated[
        bool, Query(description="Inclui os pendentes por vencimento (aceita `ate` no futuro)")
    ] = False,
) -> FluxoCaixaOut:
    return FluxoCaixaOut.de_fluxo(
        await caso.executar(ator, de, ate, hoje, agrupamento, incluir_projecao)
    )


@router.get("/financeiro/contas", response_model=ContasOut)
async def contas(ator: GestorDep, caso: ObterPosicaoContasDep, hoje: HojeDep) -> ContasOut:
    return ContasOut.de_contas(await caso.executar(ator, hoje))
