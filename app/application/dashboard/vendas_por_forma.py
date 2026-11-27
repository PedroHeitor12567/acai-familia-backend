from datetime import date

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.calculos import completar_formas
from app.domain.dashboard.modelos import VendaForma
from app.domain.dashboard.periodo import Periodo, montar_periodo
from app.domain.usuarios.entities import Usuario


class ObterVendasPorForma:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self, ator: Usuario, de: date | None, ate: date | None, hoje: date
    ) -> tuple[Periodo, list[VendaForma]]:
        exigir_gestor(ator)
        periodo = montar_periodo(de, ate, hoje)
        return periodo, completar_formas(await self._q.vendas_por_forma(periodo))
