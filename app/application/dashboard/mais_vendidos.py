from datetime import date

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.calculos import percentual
from app.domain.dashboard.modelos import OrdenarPor, ProdutoVendido
from app.domain.dashboard.periodo import Periodo, montar_periodo
from app.domain.usuarios.entities import Usuario


class ObterMaisVendidos:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self,
        ator: Usuario,
        de: date | None,
        ate: date | None,
        hoje: date,
        limite: int,
        ordenar_por: OrdenarPor,
    ) -> tuple[Periodo, list[ProdutoVendido]]:
        exigir_gestor(ator)
        periodo = montar_periodo(de, ate, hoje)
        linhas, receita_total = await self._q.mais_vendidos(periodo, ordenar_por, limite)
        return periodo, [
            ProdutoVendido(
                linha.produto_id,
                linha.nome,
                linha.quantidade,
                linha.receita,
                percentual(linha.receita, receita_total),
            )
            for linha in linhas
        ]
