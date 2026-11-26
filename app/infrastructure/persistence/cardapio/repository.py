from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.cardapio.ports import FiltrosProduto
from app.domain.cardapio.entities import Adicional, Categoria, Produto, ProdutoTamanho, Tamanho
from app.infrastructure.persistence.cardapio.models import (
    AdicionalModel,
    CategoriaModel,
    ProdutoModel,
    ProdutoTamanhoModel,
    TamanhoModel,
)
from app.infrastructure.persistence.utils import escapar_like


def _categoria(m: CategoriaModel) -> Categoria:
    return Categoria(id=m.id, nome=m.nome, ativo=m.ativo)


def _tamanho(m: TamanhoModel) -> Tamanho:
    return Tamanho(id=m.id, nome=m.nome, ativo=m.ativo)


def _produto(m: ProdutoModel) -> Produto:
    return Produto(id=m.id, nome=m.nome, categoria_id=m.categoria_id, ativo=m.ativo)


def _adicional(m: AdicionalModel) -> Adicional:
    return Adicional(id=m.id, nome=m.nome, preco=m.preco, ativo=m.ativo)


def _preco(m: ProdutoTamanhoModel) -> ProdutoTamanho:
    return ProdutoTamanho(produto_id=m.produto_id, tamanho_id=m.tamanho_id, preco=m.preco)


_Modelo = TypeVar("_Modelo", CategoriaModel, TamanhoModel, AdicionalModel, ProdutoModel)


class SqlAlchemyCardapioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _pagina(
        self,
        modelo: type[_Modelo],
        condicoes: Sequence[ColumnElement[bool]],
        limit: int,
        offset: int,
    ) -> tuple[list[_Modelo], int]:
        total = await self._s.scalar(select(func.count()).select_from(modelo).where(*condicoes))
        resultado = await self._s.scalars(
            select(modelo).where(*condicoes).order_by(modelo.id).limit(limit).offset(offset)
        )
        return list(resultado.all()), total or 0

    # --- categorias ---

    async def obter_categoria(self, categoria_id: int) -> Categoria | None:
        m = await self._s.get(CategoriaModel, categoria_id)
        return _categoria(m) if m else None

    async def obter_categoria_por_nome(self, nome: str) -> Categoria | None:
        m = await self._s.scalar(
            select(CategoriaModel).where(func.lower(CategoriaModel.nome) == nome.lower())
        )
        return _categoria(m) if m else None

    async def adicionar_categoria(self, categoria: Categoria) -> Categoria:
        m = CategoriaModel(nome=categoria.nome, ativo=categoria.ativo)
        self._s.add(m)
        await self._s.flush()
        return _categoria(m)

    async def atualizar_categoria(self, categoria: Categoria) -> Categoria:
        m = await self._s.get(CategoriaModel, categoria.id_persistido)
        if m is None:
            raise ValueError("Categoria não existe")
        m.nome, m.ativo = categoria.nome, categoria.ativo
        await self._s.flush()
        return _categoria(m)

    async def listar_categorias(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Categoria], int]:
        condicoes = [] if ativo is None else [CategoriaModel.ativo.is_(ativo)]
        itens, total = await self._pagina(CategoriaModel, condicoes, limit, offset)
        return [_categoria(m) for m in itens], total

    # --- tamanhos ---

    async def obter_tamanho(self, tamanho_id: int) -> Tamanho | None:
        m = await self._s.get(TamanhoModel, tamanho_id)
        return _tamanho(m) if m else None

    async def obter_tamanho_por_nome(self, nome: str) -> Tamanho | None:
        m = await self._s.scalar(
            select(TamanhoModel).where(func.lower(TamanhoModel.nome) == nome.lower())
        )
        return _tamanho(m) if m else None

    async def adicionar_tamanho(self, tamanho: Tamanho) -> Tamanho:
        m = TamanhoModel(nome=tamanho.nome, ativo=tamanho.ativo)
        self._s.add(m)
        await self._s.flush()
        return _tamanho(m)

    async def atualizar_tamanho(self, tamanho: Tamanho) -> Tamanho:
        m = await self._s.get(TamanhoModel, tamanho.id_persistido)
        if m is None:
            raise ValueError("Tamanho não existe")
        m.nome, m.ativo = tamanho.nome, tamanho.ativo
        await self._s.flush()
        return _tamanho(m)

    async def listar_tamanhos(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Tamanho], int]:
        condicoes = [] if ativo is None else [TamanhoModel.ativo.is_(ativo)]
        itens, total = await self._pagina(TamanhoModel, condicoes, limit, offset)
        return [_tamanho(m) for m in itens], total

    # --- adicionais ---

    async def obter_adicional(self, adicional_id: int) -> Adicional | None:
        m = await self._s.get(AdicionalModel, adicional_id)
        return _adicional(m) if m else None

    async def obter_adicional_por_nome(self, nome: str) -> Adicional | None:
        m = await self._s.scalar(
            select(AdicionalModel).where(func.lower(AdicionalModel.nome) == nome.lower())
        )
        return _adicional(m) if m else None

    async def adicionar_adicional(self, adicional: Adicional) -> Adicional:
        m = AdicionalModel(nome=adicional.nome, preco=adicional.preco, ativo=adicional.ativo)
        self._s.add(m)
        await self._s.flush()
        return _adicional(m)

    async def atualizar_adicional(self, adicional: Adicional) -> Adicional:
        m = await self._s.get(AdicionalModel, adicional.id_persistido)
        if m is None:
            raise ValueError("Adicional não existe")
        m.nome, m.preco, m.ativo = adicional.nome, adicional.preco, adicional.ativo
        await self._s.flush()
        return _adicional(m)

    async def listar_adicionais(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Adicional], int]:
        condicoes = [] if ativo is None else [AdicionalModel.ativo.is_(ativo)]
        itens, total = await self._pagina(AdicionalModel, condicoes, limit, offset)
        return [_adicional(m) for m in itens], total

    # --- produtos e preços ---

    async def obter_produto(self, produto_id: int) -> Produto | None:
        m = await self._s.get(ProdutoModel, produto_id)
        return _produto(m) if m else None

    async def obter_produto_por_nome(self, categoria_id: int, nome: str) -> Produto | None:
        m = await self._s.scalar(
            select(ProdutoModel).where(
                ProdutoModel.categoria_id == categoria_id,
                func.lower(ProdutoModel.nome) == nome.lower(),
            )
        )
        return _produto(m) if m else None

    async def adicionar_produto(self, produto: Produto) -> Produto:
        m = ProdutoModel(nome=produto.nome, categoria_id=produto.categoria_id, ativo=produto.ativo)
        self._s.add(m)
        await self._s.flush()
        return _produto(m)

    async def atualizar_produto(self, produto: Produto) -> Produto:
        m = await self._s.get(ProdutoModel, produto.id_persistido)
        if m is None:
            raise ValueError("Produto não existe")
        m.nome, m.categoria_id, m.ativo = produto.nome, produto.categoria_id, produto.ativo
        await self._s.flush()
        return _produto(m)

    async def listar_produtos(
        self, filtros: FiltrosProduto, limit: int, offset: int
    ) -> tuple[list[Produto], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.categoria_id is not None:
            condicoes.append(ProdutoModel.categoria_id == filtros.categoria_id)
        if filtros.ativo is not None:
            condicoes.append(ProdutoModel.ativo.is_(filtros.ativo))
        if filtros.q:
            condicoes.append(ProdutoModel.nome.ilike(f"%{escapar_like(filtros.q)}%", escape="\\"))
        itens, total = await self._pagina(ProdutoModel, condicoes, limit, offset)
        return [_produto(m) for m in itens], total

    async def definir_preco(self, preco: ProdutoTamanho) -> ProdutoTamanho:
        m = await self._s.get(ProdutoTamanhoModel, (preco.produto_id, preco.tamanho_id))
        if m is None:
            m = ProdutoTamanhoModel(
                produto_id=preco.produto_id, tamanho_id=preco.tamanho_id, preco=preco.preco
            )
            self._s.add(m)
        else:
            m.preco = preco.preco
        await self._s.flush()
        return _preco(m)

    async def obter_preco(self, produto_id: int, tamanho_id: int) -> ProdutoTamanho | None:
        m = await self._s.get(ProdutoTamanhoModel, (produto_id, tamanho_id))
        return _preco(m) if m else None

    async def listar_precos(self, produto_ids: Sequence[int]) -> dict[int, list[ProdutoTamanho]]:
        agrupado: dict[int, list[ProdutoTamanho]] = {pid: [] for pid in produto_ids}
        if not produto_ids:
            return agrupado
        resultado = await self._s.scalars(
            select(ProdutoTamanhoModel)
            .where(ProdutoTamanhoModel.produto_id.in_(produto_ids))
            .order_by(ProdutoTamanhoModel.produto_id, ProdutoTamanhoModel.tamanho_id)
        )
        for m in resultado.all():
            agrupado[m.produto_id].append(_preco(m))
        return agrupado
