"""Consultas agregadas do dashboard (somente leitura).

Todas fazem o filtro, o agrupamento e a soma no banco e devolvem dataclasses do domínio, nunca
entidades ORM. O recorte de datas usa o intervalo semiaberto em UTC (`limites_utc`), o que mantém
o índice parcial de `comandas` utilizável; o "dia local" só entra no GROUP BY.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ColumnElement,
    String,
    and_,
    case,
    cast,
    func,
    literal_column,
    null,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from app.domain.caixa.entities import FormaPagamento
from app.domain.dashboard.calculos import ZERO, arredondar_dinheiro
from app.domain.dashboard.fluxo import (
    FONTE_A_PAGAR,
    FONTE_A_RECEBER,
    FONTE_PAGAR,
    FONTE_RECEBER,
    FONTE_VENDA,
)
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
from app.domain.dashboard.periodo import Periodo, limites_utc
from app.domain.financeiro.entities import StatusLancamento, TipoLancamento
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.caixa.models import (
    MovimentoCaixaModel,
    PagamentoModel,
    SessaoCaixaModel,
)
from app.infrastructure.persistence.comandas.models import (
    ComandaModel,
    ItemComandaAdicionalModel,
    ItemComandaModel,
)
from app.infrastructure.persistence.estoque.models import InsumoModel
from app.infrastructure.persistence.financeiro.models import (
    CategoriaFinanceiraModel,
    LancamentoModel,
)
from app.infrastructure.persistence.sql_tempo import SqlTempo

_Consulta = Select[*tuple[Any, ...]]
_FECHADA = "fechada"
_PENDENTE = str(StatusLancamento.PENDENTE)


def _dinheiro(valor: object) -> Decimal:
    """Soma do banco (`Decimal` no PostgreSQL, `float` no SQLite) em 2 casas."""
    if valor is None:
        return ZERO
    return arredondar_dinheiro(valor if isinstance(valor, Decimal) else Decimal(str(valor)))


def _quantidade(valor: object) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _inteiro(valor: object) -> int:
    return int(valor) if isinstance(valor, int | float | Decimal | str) else 0


def _constante(texto: str) -> ColumnElement[str]:
    return cast(literal_column(f"'{texto}'"), String)


class SqlAlchemyDashboardQueries:
    def __init__(self, session: AsyncSession, fuso: str) -> None:
        self._s = session
        self._fuso = fuso

    def _tempo(self, periodo: Periodo) -> SqlTempo:
        inicio, _ = limites_utc(periodo, self._fuso)
        return SqlTempo(self._s.get_bind().dialect.name, self._fuso, inicio)

    def _fechadas_no(self, periodo: Periodo) -> list[ColumnElement[bool]]:
        inicio, fim = limites_utc(periodo, self._fuso)
        return [
            ComandaModel.status == _FECHADA,
            ComandaModel.fechada_em >= inicio,
            ComandaModel.fechada_em < fim,
        ]

    # --- vendas ------------------------------------------------------------------------------

    async def comparativo_vendas(
        self, atual: Periodo, anterior: Periodo
    ) -> tuple[TotaisVendas, TotaisVendas]:
        inicio_atual, fim_atual = limites_utc(atual, self._fuso)
        inicio_anterior, fim_anterior = limites_utc(anterior, self._fuso)
        c, i = ComandaModel, ItemComandaModel
        no_atual = and_(c.fechada_em >= inicio_atual, c.fechada_em < fim_atual)
        no_anterior = and_(c.fechada_em >= inicio_anterior, c.fechada_em < fim_anterior)

        itens = (
            select(func.coalesce(func.sum(i.quantidade), 0))
            .select_from(i)
            .join(c, c.id == i.comanda_id)
            .where(c.status == _FECHADA, no_atual)
            .correlate(None)
            .scalar_subquery()
        )
        canceladas = (
            select(func.count())
            .select_from(AuditLogModel)
            .where(
                AuditLogModel.acao == "cancelar",
                AuditLogModel.entidade == "comanda",
                AuditLogModel.criado_em >= inicio_atual,
                AuditLogModel.criado_em < fim_atual,
            )
            .correlate(None)
            .scalar_subquery()
        )
        # Uma varredura só sobre `[anterior, atual)`; cada período sai de uma soma condicional.
        linha = (
            await self._s.execute(
                select(
                    func.coalesce(func.sum(case((no_atual, c.total), else_=0)), 0),
                    func.coalesce(func.sum(case((no_atual, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((no_anterior, c.total), else_=0)), 0),
                    func.coalesce(func.sum(case((no_anterior, 1), else_=0)), 0),
                    itens,
                    canceladas,
                ).where(
                    c.status == _FECHADA,
                    c.fechada_em >= inicio_anterior,
                    c.fechada_em < fim_atual,
                )
            )
        ).one()
        return (
            TotaisVendas(
                _dinheiro(linha[0]), _inteiro(linha[1]), _inteiro(linha[4]), _inteiro(linha[5])
            ),
            TotaisVendas(_dinheiro(linha[2]), _inteiro(linha[3])),
        )

    async def vendas_por_dia(self, periodo: Periodo) -> list[VendaDia]:
        dia = self._tempo(periodo).dia_local(ComandaModel.fechada_em)
        linhas = await self._s.execute(
            select(dia.label("dia"), func.sum(ComandaModel.total), func.count())
            .where(*self._fechadas_no(periodo))
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        return [VendaDia(d, _dinheiro(total), _inteiro(qtd)) for d, total, qtd in linhas.all()]

    async def mais_vendidos(
        self, periodo: Periodo, ordenar_por: OrdenarPor, limite: int
    ) -> tuple[list[LinhaProduto], Decimal]:
        i, ultimo = ItemComandaModel, aliased(ItemComandaModel)
        adicionais = (
            select(
                func.coalesce(
                    func.sum(
                        ItemComandaAdicionalModel.quantidade
                        * ItemComandaAdicionalModel.preco_unitario
                    ),
                    0,
                )
            )
            .where(ItemComandaAdicionalModel.item_id == i.id)
            .correlate(i)
            .scalar_subquery()
        )
        por_produto = (
            select(
                i.produto_id.label("produto_id"),
                func.sum(i.quantidade).label("quantidade"),
                func.sum(i.quantidade * (i.preco_unitario + adicionais)).label("receita"),
                func.max(i.id).label("ultimo_item"),
            )
            .select_from(i)
            .join(ComandaModel, ComandaModel.id == i.comanda_id)
            .where(*self._fechadas_no(periodo))
            .group_by(i.produto_id)
            .subquery()
        )
        metrica = (
            por_produto.c.receita if ordenar_por is OrdenarPor.RECEITA else por_produto.c.quantidade
        )
        linhas = (
            await self._s.execute(
                select(
                    por_produto.c.produto_id,
                    ultimo.nome_produto,  # nome do snapshot do item mais recente do produto
                    por_produto.c.quantidade,
                    por_produto.c.receita,
                    func.sum(por_produto.c.receita).over().label("receita_total"),
                )
                .select_from(por_produto)
                .join(ultimo, ultimo.id == por_produto.c.ultimo_item)
                .order_by(metrica.desc(), ultimo.nome_produto.asc(), por_produto.c.produto_id.asc())
                .limit(limite)
            )
        ).all()
        ranking = [
            LinhaProduto(_inteiro(pid), nome, _inteiro(qtd), _dinheiro(receita))
            for pid, nome, qtd, receita, _ in linhas
        ]
        return ranking, _dinheiro(linhas[0][4]) if linhas else ZERO

    async def vendas_por_forma(self, periodo: Periodo) -> list[VendaForma]:
        p = PagamentoModel
        linhas = await self._s.execute(
            select(p.forma, func.sum(p.valor), func.count(p.id))
            .select_from(p)
            .join(ComandaModel, ComandaModel.id == p.comanda_id)
            .where(*self._fechadas_no(periodo))
            .group_by(p.forma)
        )
        return [
            VendaForma(FormaPagamento(forma), _dinheiro(valor), _inteiro(qtd))
            for forma, valor, qtd in linhas.all()
        ]

    async def vendas_por_hora(self, periodo: Periodo) -> list[VendaHora]:
        hora = self._tempo(periodo).hora_local(ComandaModel.fechada_em)
        linhas = await self._s.execute(
            select(hora.label("hora"), func.count(), func.sum(ComandaModel.total))
            .where(*self._fechadas_no(periodo))
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        return [
            VendaHora(_inteiro(h), _inteiro(qtd), _dinheiro(total))
            for h, qtd, total in linhas.all()
        ]

    # --- estoque -----------------------------------------------------------------------------

    async def insumos_criticos(self) -> list[InsumoCritico]:
        m = InsumoModel
        linhas = await self._s.execute(
            select(m.id, m.nome, m.unidade, m.estoque_atual, m.estoque_minimo).where(
                m.ativo.is_(True), m.estoque_minimo > 0, m.estoque_atual <= m.estoque_minimo
            )
        )
        return [
            InsumoCritico(id_, nome, unidade, _quantidade(atual), _quantidade(minimo))
            for id_, nome, unidade, atual, minimo in linhas.all()
        ]

    # --- financeiro --------------------------------------------------------------------------

    async def fatos_fluxo_caixa(self, periodo: Periodo, incluir_projecao: bool) -> list[FatoCaixa]:
        p, c, lanc = PagamentoModel, ComandaModel, LancamentoModel
        categoria_nula = cast(null(), String)
        dia_venda = self._tempo(periodo).dia_local(c.fechada_em)

        def lancamentos(fonte: str, tipo: TipoLancamento, status: StatusLancamento) -> _Consulta:
            data = lanc.data_pagamento if status is StatusLancamento.PAGO else lanc.vencimento
            return (
                select(
                    _constante(fonte).label("fonte"),
                    data.label("dia"),
                    categoria_nula.label("categoria"),
                    func.sum(lanc.valor).label("valor"),
                )
                .where(
                    lanc.tipo == str(tipo),
                    lanc.status == str(status),
                    data >= periodo.de,
                    data <= periodo.ate,
                )
                .group_by(literal_column("2"))
            )

        consultas: list[_Consulta] = [
            select(
                _constante(FONTE_VENDA).label("fonte"),
                dia_venda.label("dia"),
                categoria_nula.label("categoria"),
                func.sum(p.valor).label("valor"),
            )
            .select_from(p)
            .join(c, c.id == p.comanda_id)
            .where(*self._fechadas_no(periodo))
            .group_by(literal_column("2")),
            lancamentos(FONTE_RECEBER, TipoLancamento.RECEBER, StatusLancamento.PAGO),
            # Despesas pagas, abertas por categoria (alimenta `saidas_por_categoria`).
            select(
                _constante(FONTE_PAGAR).label("fonte"),
                lanc.data_pagamento.label("dia"),
                CategoriaFinanceiraModel.nome.label("categoria"),
                func.sum(lanc.valor).label("valor"),
            )
            .select_from(lanc)
            .join(CategoriaFinanceiraModel, CategoriaFinanceiraModel.id == lanc.categoria_id)
            .where(
                lanc.tipo == str(TipoLancamento.PAGAR),
                lanc.status == str(StatusLancamento.PAGO),
                lanc.data_pagamento >= periodo.de,
                lanc.data_pagamento <= periodo.ate,
            )
            .group_by(literal_column("2"), literal_column("3")),
        ]
        if incluir_projecao:
            consultas.append(
                lancamentos(FONTE_A_RECEBER, TipoLancamento.RECEBER, StatusLancamento.PENDENTE)
            )
            consultas.append(
                lancamentos(FONTE_A_PAGAR, TipoLancamento.PAGAR, StatusLancamento.PENDENTE)
            )
        linhas = await self._s.execute(union_all(*consultas))
        return [
            FatoCaixa(fonte, dia, _dinheiro(valor), categoria)
            for fonte, dia, categoria, valor in linhas.all()
        ]

    async def posicao_contas(self, hoje: date) -> dict[TipoLancamento, PosicaoConta]:
        lanc = LancamentoModel
        em_7_dias = hoje + timedelta(days=7)
        atrasado = lanc.vencimento < hoje
        vence_hoje = lanc.vencimento == hoje
        proximos_7 = and_(lanc.vencimento > hoje, lanc.vencimento <= em_7_dias)

        def valor_se(condicao: ColumnElement[bool]) -> ColumnElement[Any]:
            return func.coalesce(func.sum(case((condicao, lanc.valor), else_=0)), 0)

        def qtd_se(condicao: ColumnElement[bool]) -> ColumnElement[Any]:
            return func.coalesce(func.sum(case((condicao, 1), else_=0)), 0)

        linhas = await self._s.execute(
            select(
                lanc.tipo,
                func.coalesce(func.sum(lanc.valor), 0),
                func.count(),
                valor_se(atrasado),
                qtd_se(atrasado),
                valor_se(vence_hoje),
                qtd_se(vence_hoje),
                valor_se(proximos_7),
                qtd_se(proximos_7),
            )
            .where(lanc.status == _PENDENTE)
            .group_by(lanc.tipo)
        )
        por_tipo: dict[TipoLancamento, PosicaoConta] = {
            tipo: PosicaoConta(tipo, ZERO, 0, ZERO, 0, ZERO, 0, ZERO, 0) for tipo in TipoLancamento
        }
        for tipo, total, qtd, v_atr, q_atr, v_hoje, q_hoje, v_7, q_7 in linhas.all():
            por_tipo[TipoLancamento(tipo)] = PosicaoConta(
                TipoLancamento(tipo),
                _dinheiro(total),
                _inteiro(qtd),
                _dinheiro(v_atr),
                _inteiro(q_atr),
                _dinheiro(v_hoje),
                _inteiro(q_hoje),
                _dinheiro(v_7),
                _inteiro(q_7),
            )
        return por_tipo

    async def proximos_vencimentos(self, hoje: date, limite: int) -> list[Vencimento]:
        lanc = LancamentoModel
        linhas = await self._s.execute(
            select(lanc.id, lanc.tipo, lanc.descricao, lanc.valor, lanc.vencimento)
            .where(lanc.status == _PENDENTE)
            .order_by(lanc.vencimento.asc(), lanc.id.asc())  # atrasados vêm primeiro
            .limit(limite)
        )
        return [
            Vencimento(id_, TipoLancamento(tipo), descricao, _dinheiro(valor), venc, venc < hoje)
            for id_, tipo, descricao, valor, venc in linhas.all()
        ]

    # --- visão geral -------------------------------------------------------------------------

    async def comandas_abertas(self) -> int:
        total = await self._s.scalar(
            select(func.count()).select_from(ComandaModel).where(ComandaModel.status == "aberta")
        )
        return total or 0

    async def caixa_aberto(self) -> CaixaAberto | None:
        s, p, m = SessaoCaixaModel, PagamentoModel, MovimentoCaixaModel

        def movimentos(tipo: str) -> ColumnElement[Any]:
            return (
                select(func.coalesce(func.sum(m.valor), 0))
                .where(m.sessao_id == s.id, m.tipo == tipo)
                .correlate(s)
                .scalar_subquery()
            )

        dinheiro = (
            select(func.coalesce(func.sum(p.valor), 0))
            .where(p.sessao_id == s.id, p.forma == str(FormaPagamento.DINHEIRO))
            .correlate(s)
            .scalar_subquery()
        )
        linha = (
            await self._s.execute(
                select(
                    s.id,
                    s.valor_abertura,
                    dinheiro,
                    movimentos("suprimento"),
                    movimentos("sangria"),
                ).where(s.status == "aberta")
            )
        ).first()
        if linha is None:
            return None
        return CaixaAberto(
            _inteiro(linha[0]),
            _dinheiro(linha[1]),
            _dinheiro(linha[2]),
            _dinheiro(linha[3]),
            _dinheiro(linha[4]),
        )
