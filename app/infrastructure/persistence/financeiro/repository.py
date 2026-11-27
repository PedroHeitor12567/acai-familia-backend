from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.financeiro.ports import FiltrosLancamento
from app.domain.caixa.entities import FormaPagamento
from app.domain.exceptions import (
    CategoriaFinanceiraNaoEncontrada,
    LancamentoNaoEncontrado,
    NomeJaCadastrado,
)
from app.domain.financeiro.entities import (
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.infrastructure.persistence.financeiro.models import (
    CategoriaFinanceiraModel,
    LancamentoModel,
)
from app.infrastructure.persistence.utils import escapar_like


def _categoria(m: CategoriaFinanceiraModel) -> CategoriaFinanceira:
    return CategoriaFinanceira(id=m.id, nome=m.nome, tipo=TipoCategoria(m.tipo), ativo=m.ativo)


def _lancamento(m: LancamentoModel) -> Lancamento:
    return Lancamento(
        id=m.id,
        tipo=TipoLancamento(m.tipo),
        descricao=m.descricao,
        valor=m.valor,
        vencimento=m.vencimento,
        categoria_id=m.categoria_id,
        contraparte=m.contraparte,
        observacao=m.observacao,
        status=StatusLancamento(m.status),
        data_pagamento=m.data_pagamento,
        forma_pagamento=FormaPagamento(m.forma_pagamento) if m.forma_pagamento else None,
        criado_por_id=m.criado_por_id,
        baixado_por_id=m.baixado_por_id,
    )


class SqlAlchemyFinanceiroRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def adicionar_categoria(self, categoria: CategoriaFinanceira) -> CategoriaFinanceira:
        m = CategoriaFinanceiraModel(
            nome=categoria.nome, tipo=str(categoria.tipo), ativo=categoria.ativo
        )
        self._s.add(m)
        try:
            await self._s.flush()
        except IntegrityError as erro:
            raise NomeJaCadastrado("categoria_financeira") from erro
        return _categoria(m)

    async def obter_categoria(self, categoria_id: int) -> CategoriaFinanceira | None:
        m = await self._s.get(CategoriaFinanceiraModel, categoria_id)
        return _categoria(m) if m else None

    async def obter_categoria_por_nome(
        self, nome: str, tipo: TipoCategoria
    ) -> CategoriaFinanceira | None:
        m = await self._s.scalar(
            select(CategoriaFinanceiraModel).where(
                CategoriaFinanceiraModel.tipo == str(tipo),
                func.lower(CategoriaFinanceiraModel.nome) == nome.lower(),
            )
        )
        return _categoria(m) if m else None

    async def atualizar_categoria(self, categoria: CategoriaFinanceira) -> CategoriaFinanceira:
        m = await self._s.get(CategoriaFinanceiraModel, categoria.id_persistido)
        if m is None:
            raise CategoriaFinanceiraNaoEncontrada
        m.nome, m.ativo = categoria.nome, categoria.ativo
        try:
            await self._s.flush()
        except IntegrityError as erro:
            raise NomeJaCadastrado("categoria_financeira") from erro
        return _categoria(m)

    async def listar_categorias(
        self, tipo: TipoCategoria | None, ativo: bool | None
    ) -> list[CategoriaFinanceira]:
        consulta = select(CategoriaFinanceiraModel).order_by(
            CategoriaFinanceiraModel.tipo, func.lower(CategoriaFinanceiraModel.nome)
        )
        if tipo is not None:
            consulta = consulta.where(CategoriaFinanceiraModel.tipo == str(tipo))
        if ativo is not None:
            consulta = consulta.where(CategoriaFinanceiraModel.ativo == ativo)
        return [_categoria(m) for m in (await self._s.scalars(consulta)).all()]

    async def adicionar_lancamento(self, lancamento: Lancamento) -> Lancamento:
        m = LancamentoModel(
            tipo=str(lancamento.tipo),
            descricao=lancamento.descricao,
            valor=lancamento.valor,
            vencimento=lancamento.vencimento,
            categoria_id=lancamento.categoria_id,
            contraparte=lancamento.contraparte,
            observacao=lancamento.observacao,
            status=str(lancamento.status),
            data_pagamento=lancamento.data_pagamento,
            forma_pagamento=str(lancamento.forma_pagamento) if lancamento.forma_pagamento else None,
            criado_por_id=lancamento.criado_por_id,
            baixado_por_id=lancamento.baixado_por_id,
        )
        self._s.add(m)
        await self._s.flush()
        return _lancamento(m)

    async def obter_lancamento(
        self, lancamento_id: int, *, para_atualizar: bool = False
    ) -> Lancamento | None:
        consulta = (
            select(LancamentoModel)
            .where(LancamentoModel.id == lancamento_id)
            .execution_options(populate_existing=True)
        )
        if para_atualizar:
            consulta = consulta.with_for_update()
        m = await self._s.scalar(consulta)
        return _lancamento(m) if m else None

    async def atualizar_lancamento(self, lancamento: Lancamento) -> Lancamento:
        m = await self._s.get(LancamentoModel, lancamento.id_persistido)
        if m is None:
            raise LancamentoNaoEncontrado
        m.descricao, m.valor, m.vencimento = (
            lancamento.descricao,
            lancamento.valor,
            lancamento.vencimento,
        )
        m.categoria_id = lancamento.categoria_id
        m.contraparte, m.observacao = lancamento.contraparte, lancamento.observacao
        m.status = str(lancamento.status)
        m.data_pagamento = lancamento.data_pagamento
        m.forma_pagamento = str(lancamento.forma_pagamento) if lancamento.forma_pagamento else None
        m.baixado_por_id = lancamento.baixado_por_id
        await self._s.flush()
        return _lancamento(m)

    async def listar_lancamentos(
        self, filtros: FiltrosLancamento, limit: int, offset: int
    ) -> tuple[list[Lancamento], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.tipo is not None:
            condicoes.append(LancamentoModel.tipo == str(filtros.tipo))
        if filtros.status is not None:
            condicoes.append(LancamentoModel.status == str(filtros.status))
        if filtros.categoria_id is not None:
            condicoes.append(LancamentoModel.categoria_id == filtros.categoria_id)
        if filtros.atrasados:
            if filtros.hoje is None:
                raise ValueError("`hoje` é obrigatório para filtrar atrasados")
            condicoes.append(LancamentoModel.status == str(StatusLancamento.PENDENTE))
            condicoes.append(LancamentoModel.vencimento < filtros.hoje)
        if filtros.vencimento_de is not None:
            condicoes.append(LancamentoModel.vencimento >= filtros.vencimento_de)
        if filtros.vencimento_ate is not None:
            condicoes.append(LancamentoModel.vencimento <= filtros.vencimento_ate)
        if filtros.contraparte:
            condicoes.append(
                LancamentoModel.contraparte.ilike(
                    f"%{escapar_like(filtros.contraparte)}%", escape="\\"
                )
            )

        total = await self._s.scalar(
            select(func.count()).select_from(LancamentoModel).where(*condicoes)
        )
        pendente = LancamentoModel.status == str(StatusLancamento.PENDENTE)
        resultado = await self._s.scalars(
            select(LancamentoModel)
            .where(*condicoes)
            .order_by(
                case((pendente, 0), else_=1),
                case((pendente, LancamentoModel.vencimento)).asc(),
                func.coalesce(LancamentoModel.data_pagamento, LancamentoModel.vencimento).desc(),
                LancamentoModel.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [_lancamento(m) for m in resultado.all()], total or 0
