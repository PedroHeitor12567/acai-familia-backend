from collections.abc import Sequence
from typing import Any

from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.estoque.entities import ItemFichaTecnica
from app.domain.estoque.regras import validar_ficha
from app.domain.exceptions import (
    AdicionalNaoEncontrado,
    FichaTecnicaInvalida,
    ProdutoNaoEncontrado,
    TamanhoNaoEncontrado,
)
from app.domain.usuarios.entities import Usuario


def _itens_para_auditoria(itens: Sequence[ItemFichaTecnica]) -> list[dict[str, Any]]:
    return [{"insumo_id": i.insumo_id, "quantidade": str(i.quantidade)} for i in itens]


async def _validar_insumos(uow: UnitOfWork, itens: Sequence[ItemFichaTecnica]) -> None:
    for item in itens:
        insumo = await uow.estoque.obter_insumo(item.insumo_id)
        if insumo is None:
            raise FichaTecnicaInvalida("insumo_inexistente")
        if not insumo.ativo:
            raise FichaTecnicaInvalida("insumo_inativo")


class DefinirFichaTecnica:
    """Substitui a receita inteira de (produto, tamanho) de forma atômica: ou grava a lista
    nova completa, ou nada muda. Lista vazia limpa a receita."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        produto_id: int,
        tamanho_id: int,
        itens: Sequence[ItemFichaTecnica],
    ) -> list[ItemFichaTecnica]:
        exigir_gestor(ator)
        produto = await self._uow.cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        if await self._uow.cardapio.obter_tamanho(tamanho_id) is None:
            raise TamanhoNaoEncontrado
        if not produto.ativo:
            raise FichaTecnicaInvalida("produto_inativo")
        if await self._uow.cardapio.obter_preco(produto_id, tamanho_id) is None:
            raise FichaTecnicaInvalida("produto_sem_tamanho")
        novos = validar_ficha(itens)
        await _validar_insumos(self._uow, novos)

        await self._uow.ficha_tecnica.substituir_ficha_produto(produto_id, tamanho_id, novos)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "definir_ficha",
            "ficha_tecnica",
            f"{produto_id}:{tamanho_id}",
            {"itens": _itens_para_auditoria(novos)},
        )
        await self._uow.commit()
        return sorted(novos, key=lambda i: i.insumo_id)  # mesma ordem do GET


class ObterFichaTecnica:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, produto_id: int, tamanho_id: int
    ) -> list[ItemFichaTecnica]:
        exigir_gestor(ator)
        if await self._uow.cardapio.obter_produto(produto_id) is None:
            raise ProdutoNaoEncontrado
        if await self._uow.cardapio.obter_tamanho(tamanho_id) is None:
            raise TamanhoNaoEncontrado
        return await self._uow.ficha_tecnica.obter_ficha_produto(produto_id, tamanho_id)


class DefinirFichaAdicional:
    """Ficha técnica de um adicional (granola, leite ninho...): consumo por porção."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, adicional_id: int, itens: Sequence[ItemFichaTecnica]
    ) -> list[ItemFichaTecnica]:
        exigir_gestor(ator)
        adicional = await self._uow.cardapio.obter_adicional(adicional_id)
        if adicional is None:
            raise AdicionalNaoEncontrado
        if not adicional.ativo:
            raise FichaTecnicaInvalida("adicional_inativo")
        novos = validar_ficha(itens)
        await _validar_insumos(self._uow, novos)

        await self._uow.ficha_tecnica.substituir_ficha_adicional(adicional_id, novos)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "definir_ficha",
            "ficha_tecnica_adicional",
            str(adicional_id),
            {"itens": _itens_para_auditoria(novos)},
        )
        await self._uow.commit()
        return sorted(novos, key=lambda i: i.insumo_id)  # mesma ordem do GET


class ObterFichaAdicional:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, adicional_id: int) -> list[ItemFichaTecnica]:
        exigir_gestor(ator)
        if await self._uow.cardapio.obter_adicional(adicional_id) is None:
            raise AdicionalNaoEncontrado
        return await self._uow.ficha_tecnica.obter_ficha_adicional(adicional_id)
