from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.caixa.ports import FiltrosSessao
from app.domain.caixa.entities import (
    FormaPagamento,
    MovimentoCaixa,
    Pagamento,
    SessaoCaixa,
    StatusSessao,
    TipoMovimento,
)
from app.domain.exceptions import OperacaoNaoPermitida, SessaoCaixaNaoEncontrada
from app.infrastructure.persistence.caixa.models import (
    MovimentoCaixaModel,
    PagamentoModel,
    SessaoCaixaModel,
)


def _sessao(m: SessaoCaixaModel) -> SessaoCaixa:
    return SessaoCaixa(
        id=m.id,
        status=StatusSessao(m.status),
        valor_abertura=m.valor_abertura,
        aberta_por_id=m.aberta_por_id,
        fechada_por_id=m.fechada_por_id,
        aberta_em=m.aberta_em,
        fechada_em=m.fechada_em,
        valor_esperado=m.valor_esperado,
        valor_contado=m.valor_contado,
        diferenca=m.diferenca,
        observacao=m.observacao,
    )


def _movimento(m: MovimentoCaixaModel) -> MovimentoCaixa:
    return MovimentoCaixa(
        id=m.id,
        sessao_id=m.sessao_id,
        tipo=TipoMovimento(m.tipo),
        valor=m.valor,
        motivo=m.motivo,
        criado_por_id=m.criado_por_id,
        criado_em=m.criado_em,
    )


def _pagamento(m: PagamentoModel) -> Pagamento:
    return Pagamento(
        id=m.id,
        comanda_id=m.comanda_id,
        sessao_id=m.sessao_id,
        forma=FormaPagamento(m.forma),
        valor=m.valor,
        valor_recebido=m.valor_recebido,
        criado_por_id=m.criado_por_id,
        criado_em=m.criado_em,
    )


class SqlAlchemyCaixaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def adicionar_sessao(self, sessao: SessaoCaixa) -> SessaoCaixa:
        m = SessaoCaixaModel(
            status=str(sessao.status),
            valor_abertura=sessao.valor_abertura,
            aberta_por_id=sessao.aberta_por_id,
            aberta_em=sessao.aberta_em,
            observacao=sessao.observacao,
        )
        self._s.add(m)
        try:
            await self._s.flush()
        except IntegrityError as erro:
            detalhe = str(erro.orig)
            if "ux_caixa_sessao_aberta" in detalhe or "caixa_sessoes.status" in detalhe:
                raise OperacaoNaoPermitida("caixa_ja_aberto") from erro
            raise
        return _sessao(m)

    async def obter_sessao(
        self, sessao_id: int, *, para_atualizar: bool = False
    ) -> SessaoCaixa | None:
        consulta = (
            select(SessaoCaixaModel)
            .where(SessaoCaixaModel.id == sessao_id)
            .execution_options(populate_existing=True)
        )
        if para_atualizar:
            consulta = consulta.with_for_update()
        m = await self._s.scalar(consulta)
        return _sessao(m) if m else None

    async def obter_sessao_aberta(self, *, para_atualizar: bool = False) -> SessaoCaixa | None:
        consulta = (
            select(SessaoCaixaModel)
            .where(SessaoCaixaModel.status == str(StatusSessao.ABERTA))
            .execution_options(populate_existing=True)
        )
        if para_atualizar:
            consulta = consulta.with_for_update()
        m = await self._s.scalar(consulta)
        return _sessao(m) if m else None

    async def listar_sessoes(
        self, filtros: FiltrosSessao, limit: int, offset: int
    ) -> tuple[list[SessaoCaixa], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.status is not None:
            condicoes.append(SessaoCaixaModel.status == str(filtros.status))
        if filtros.de is not None:
            condicoes.append(SessaoCaixaModel.aberta_em >= filtros.de)
        if filtros.ate is not None:
            condicoes.append(SessaoCaixaModel.aberta_em <= filtros.ate)
        total = await self._s.scalar(
            select(func.count()).select_from(SessaoCaixaModel).where(*condicoes)
        )
        resultado = await self._s.scalars(
            select(SessaoCaixaModel)
            .where(*condicoes)
            .order_by(SessaoCaixaModel.aberta_em.desc(), SessaoCaixaModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_sessao(m) for m in resultado.all()], total or 0

    async def marcar_sessao_fechada(self, sessao: SessaoCaixa) -> None:
        m = await self._s.get(SessaoCaixaModel, sessao.id_persistido)
        if m is None:
            raise SessaoCaixaNaoEncontrada
        m.status = str(sessao.status)
        m.fechada_por_id, m.fechada_em = sessao.fechada_por_id, sessao.fechada_em
        m.valor_esperado, m.valor_contado = sessao.valor_esperado, sessao.valor_contado
        m.diferenca, m.observacao = sessao.diferenca, sessao.observacao
        await self._s.flush()

    async def adicionar_movimento(self, movimento: MovimentoCaixa) -> MovimentoCaixa:
        m = MovimentoCaixaModel(
            sessao_id=movimento.sessao_id,
            tipo=str(movimento.tipo),
            valor=movimento.valor,
            motivo=movimento.motivo,
            criado_por_id=movimento.criado_por_id,
            criado_em=movimento.criado_em,
        )
        self._s.add(m)
        await self._s.flush()
        return _movimento(m)

    async def listar_movimentos(self, sessao_id: int) -> list[MovimentoCaixa]:
        resultado = await self._s.scalars(
            select(MovimentoCaixaModel)
            .where(MovimentoCaixaModel.sessao_id == sessao_id)
            .order_by(MovimentoCaixaModel.id)
            .execution_options(populate_existing=True)
        )
        return [_movimento(m) for m in resultado.all()]

    async def adicionar_pagamento(self, pagamento: Pagamento) -> Pagamento:
        m = PagamentoModel(
            comanda_id=pagamento.comanda_id,
            sessao_id=pagamento.sessao_id,
            forma=str(pagamento.forma),
            valor=pagamento.valor,
            valor_recebido=pagamento.valor_recebido,
            criado_por_id=pagamento.criado_por_id,
            criado_em=pagamento.criado_em,
        )
        self._s.add(m)
        await self._s.flush()
        return _pagamento(m)

    async def listar_pagamentos_da_sessao(self, sessao_id: int) -> list[Pagamento]:
        resultado = await self._s.scalars(
            select(PagamentoModel)
            .where(PagamentoModel.sessao_id == sessao_id)
            .order_by(PagamentoModel.id)
            .execution_options(populate_existing=True)
        )
        return [_pagamento(m) for m in resultado.all()]

    async def listar_pagamentos_da_comanda(self, comanda_id: int) -> list[Pagamento]:
        resultado = await self._s.scalars(
            select(PagamentoModel)
            .where(PagamentoModel.comanda_id == comanda_id)
            .order_by(PagamentoModel.id)
            .execution_options(populate_existing=True)
        )
        return [_pagamento(m) for m in resultado.all()]
