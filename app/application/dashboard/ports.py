from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.dashboard.modelos import (
    CaixaAberto,
    FatoCaixa,
    InsumoCritico,
    LinhaProduto,
    OrdenarPor,
    PosicaoConta,
    TotaisVendas,
    Vencimento,
    VendaDia,
    VendaForma,
    VendaHora,
)
from app.domain.dashboard.periodo import Periodo
from app.domain.financeiro.entities import TipoLancamento


class DashboardQueries(Protocol):
    """Consultas agregadas de **leitura** (GROUP BY no banco). Nunca devolvem entidades nem
    linhas de comanda/pagamento; os períodos chegam em datas locais e o adaptador converte
    para o fuso da loja."""

    async def comparativo_vendas(
        self, atual: Periodo, anterior: Periodo
    ) -> tuple[TotaisVendas, TotaisVendas]:
        """Totais dos dois períodos numa consulta só. Itens vendidos e canceladas só são
        preenchidos para o período `atual`."""
        ...

    async def vendas_por_dia(self, periodo: Periodo) -> list[VendaDia]: ...

    async def mais_vendidos(
        self, periodo: Periodo, ordenar_por: OrdenarPor, limite: int
    ) -> tuple[list[LinhaProduto], Decimal]:
        """Ranking já ordenado e limitado + a receita de itens de **todos** os produtos."""
        ...

    async def vendas_por_forma(self, periodo: Periodo) -> list[VendaForma]: ...

    async def vendas_por_hora(self, periodo: Periodo) -> list[VendaHora]: ...

    async def insumos_criticos(self) -> list[InsumoCritico]: ...

    async def fatos_fluxo_caixa(self, periodo: Periodo, incluir_projecao: bool) -> list[FatoCaixa]:
        """Vendas (pagamentos), lançamentos pagos e, opcionalmente, pendentes, agregados por
        dia e numa consulta só."""
        ...

    async def posicao_contas(self, hoje: date) -> dict[TipoLancamento, PosicaoConta]: ...

    async def proximos_vencimentos(self, hoje: date, limite: int) -> list[Vencimento]: ...

    async def comandas_abertas(self) -> int: ...

    async def caixa_aberto(self) -> CaixaAberto | None: ...
