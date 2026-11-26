from decimal import Decimal
from typing import Any

from app.application.cardapio.dto import ProdutoComPrecos
from app.application.cardapio.ports import FiltrosProduto
from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.cardapio.entities import Produto, ProdutoTamanho
from app.domain.exceptions import (
    CategoriaNaoEncontrada,
    NomeJaCadastrado,
    OperacaoNaoPermitida,
    ProdutoNaoEncontrado,
    TamanhoNaoEncontrado,
)
from app.domain.usuarios.entities import Usuario


async def _com_precos(uow: UnitOfWork, produtos: list[Produto]) -> list[ProdutoComPrecos]:
    precos = await uow.cardapio.listar_precos([p.id_persistido for p in produtos])
    return [ProdutoComPrecos(p, precos.get(p.id_persistido, [])) for p in produtos]


class CriarProduto:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, nome: str, categoria_id: int) -> ProdutoComPrecos:
        exigir_gestor(ator)
        categoria = await self._uow.cardapio.obter_categoria(categoria_id)
        if categoria is None:
            raise CategoriaNaoEncontrada
        if not categoria.ativo:
            raise OperacaoNaoPermitida("categoria_inativa")
        if await self._uow.cardapio.obter_produto_por_nome(categoria_id, nome) is not None:
            raise NomeJaCadastrado("produto")
        produto = await self._uow.cardapio.adicionar_produto(
            Produto(nome=nome, categoria_id=categoria_id)
        )
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "criar",
            "produto",
            str(produto.id),
            {"nome": nome, "categoria_id": categoria_id},
        )
        await self._uow.commit()
        return ProdutoComPrecos(produto, [])


class AtualizarProduto:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        produto_id: int,
        nome: str | None = None,
        categoria_id: int | None = None,
    ) -> ProdutoComPrecos:
        exigir_gestor(ator)
        produto = await self._uow.cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        novo_nome = nome if nome is not None else produto.nome
        nova_categoria = categoria_id if categoria_id is not None else produto.categoria_id

        if nova_categoria != produto.categoria_id:
            categoria = await self._uow.cardapio.obter_categoria(nova_categoria)
            if categoria is None:
                raise CategoriaNaoEncontrada
            if not categoria.ativo:
                raise OperacaoNaoPermitida("categoria_inativa")
        if (novo_nome, nova_categoria) != (produto.nome, produto.categoria_id):
            existente = await self._uow.cardapio.obter_produto_por_nome(nova_categoria, novo_nome)
            if existente is not None and existente.id != produto.id:
                raise NomeJaCadastrado("produto")

        diff: dict[str, Any] = {}
        if novo_nome != produto.nome:
            diff["nome"] = {"antes": produto.nome, "depois": novo_nome}
        if nova_categoria != produto.categoria_id:
            diff["categoria_id"] = {"antes": produto.categoria_id, "depois": nova_categoria}
        if not diff:
            return (await _com_precos(self._uow, [produto]))[0]

        produto.nome, produto.categoria_id = novo_nome, nova_categoria
        atualizado = await self._uow.cardapio.atualizar_produto(produto)
        await self._uow.auditoria.registrar(
            ator.id_persistido, "atualizar", "produto", str(produto_id), diff
        )
        await self._uow.commit()
        return (await _com_precos(self._uow, [atualizado]))[0]


class AlterarStatusProduto:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, produto_id: int, ativo: bool) -> ProdutoComPrecos:
        exigir_gestor(ator)
        produto = await self._uow.cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        if produto.ativo != ativo:
            produto.ativo = ativo
            produto = await self._uow.cardapio.atualizar_produto(produto)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "ativar" if ativo else "desativar",
                "produto",
                str(produto_id),
                {"ativo": {"antes": not ativo, "depois": ativo}},
            )
            await self._uow.commit()
        return (await _com_precos(self._uow, [produto]))[0]


class DefinirPrecoProduto:
    """Cria ou altera o preço de um produto em um tamanho."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, produto_id: int, tamanho_id: int, preco: Decimal
    ) -> ProdutoComPrecos:
        exigir_gestor(ator)
        produto = await self._uow.cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        tamanho = await self._uow.cardapio.obter_tamanho(tamanho_id)
        if tamanho is None:
            raise TamanhoNaoEncontrado
        if not tamanho.ativo:
            raise OperacaoNaoPermitida("tamanho_inativo")
        novo = ProdutoTamanho(produto_id, tamanho_id, preco)  # valida o preço
        antes = await self._uow.cardapio.obter_preco(produto_id, tamanho_id)
        if antes is None or antes.preco != preco:
            await self._uow.cardapio.definir_preco(novo)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "definir_preco",
                "produto",
                str(produto_id),
                {
                    "tamanho_id": tamanho_id,
                    "preco": {"antes": str(antes.preco) if antes else None, "depois": str(preco)},
                },
            )
            await self._uow.commit()
        return (await _com_precos(self._uow, [produto]))[0]


class ObterProduto:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, produto_id: int) -> ProdutoComPrecos:
        produto = await self._uow.cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        return (await _com_precos(self._uow, [produto]))[0]


class ListarProdutos:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, filtros: FiltrosProduto, limit: int, offset: int
    ) -> tuple[list[ProdutoComPrecos], int]:
        produtos, total = await self._uow.cardapio.listar_produtos(filtros, limit, offset)
        return await _com_precos(self._uow, produtos), total
