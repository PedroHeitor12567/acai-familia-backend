from datetime import date

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.calculos import preencher_serie
from app.domain.dashboard.modelos import PontoSerie
from app.domain.dashboard.periodo import Agrupamento, Periodo, montar_periodo, validar_agrupamento
from app.domain.usuarios.entities import Usuario


class ObterSerieVendas:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self,
        ator: Usuario,
        de: date | None,
        ate: date | None,
        hoje: date,
        agrupamento: Agrupamento,
    ) -> tuple[Periodo, list[PontoSerie]]:
        exigir_gestor(ator)
        periodo = montar_periodo(de, ate, hoje)
        validar_agrupamento(periodo, agrupamento)
        vendas = await self._q.vendas_por_dia(periodo)
        return periodo, preencher_serie(periodo, agrupamento, vendas)
