from datetime import date
from decimal import Decimal

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.calculos import calcular_variacoes, ticket_medio
from app.domain.dashboard.modelos import ResumoVendas, TotaisVendas, Variacoes
from app.domain.dashboard.periodo import montar_periodo
from app.domain.usuarios.entities import Usuario


def comparar(atual: TotaisVendas, anterior: TotaisVendas) -> tuple[Decimal, Decimal, Variacoes]:
    """Ticket médio dos dois lados e as variações percentuais (`None` se o anterior é zero)."""
    ticket_atual = ticket_medio(atual.faturamento, atual.qtd_comandas)
    ticket_anterior = ticket_medio(anterior.faturamento, anterior.qtd_comandas)
    variacoes = calcular_variacoes(
        (atual.faturamento, anterior.faturamento),
        (atual.qtd_comandas, anterior.qtd_comandas),
        (ticket_atual, ticket_anterior),
    )
    return ticket_atual, ticket_anterior, variacoes


class ObterResumoVendas:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self, ator: Usuario, de: date | None, ate: date | None, hoje: date
    ) -> ResumoVendas:
        exigir_gestor(ator)
        periodo = montar_periodo(de, ate, hoje)
        anterior_periodo = periodo.anterior()
        atual, anterior = await self._q.comparativo_vendas(periodo, anterior_periodo)
        ticket_atual, ticket_anterior, variacoes = comparar(atual, anterior)
        return ResumoVendas(
            periodo=periodo,
            atual=atual,
            ticket_medio=ticket_atual,
            periodo_anterior=anterior_periodo,
            anterior=anterior,
            ticket_medio_anterior=ticket_anterior,
            variacao_pct=variacoes,
        )
