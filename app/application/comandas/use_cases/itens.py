from collections.abc import Sequence
from dataclasses import dataclass

from app.application.shared.permissoes import exigir_operador_comanda
from app.application.unit_of_work import UnitOfWork
from app.domain.comandas.entities import AdicionalItem, Comanda, ItemComanda
from app.domain.comandas.regras import (
    exigir_aberta,
    validar_observacao,
    validar_quantidade_item,
)
from app.domain.exceptions import (
    AdicionalNaoEncontrado,
    ComandaNaoEncontrada,
    ItemComandaInvalido,
    ItemComandaNaoEncontrado,
    ProdutoNaoEncontrado,
    TamanhoNaoEncontrado,
)
from app.domain.usuarios.entities import Usuario


@dataclass(frozen=True)
class AdicionalPedido:
    adicional_id: int
    quantidade: int = 1


async def _travar_comanda_aberta(uow: UnitOfWork, comanda_id: int) -> Comanda:
    """Trava a comanda (`FOR UPDATE`) e exige que esteja aberta já com o lock: assim nada muda
    os itens enquanto um fechamento está em curso (e vice-versa)."""
    comanda = await uow.comandas.obter(comanda_id, para_atualizar=True)
    if comanda is None:
        raise ComandaNaoEncontrada
    exigir_aberta(comanda)
    return comanda


async def _recarregar(uow: UnitOfWork, comanda_id: int) -> Comanda:
    comanda = await uow.comandas.obter(comanda_id)
    if comanda is None:  # pragma: no cover - acabou de ser lida com lock
        raise ComandaNaoEncontrada
    return comanda


class AdicionarItem:
    """Lança um item: valida produto, tamanho e adicionais (existentes e ativos) e congela o
    preço e os nomes de agora. Mudar o cardápio depois não altera o que já foi lançado."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        comanda_id: int,
        produto_id: int,
        tamanho_id: int,
        quantidade: int = 1,
        adicionais: Sequence[AdicionalPedido] = (),
        observacao: str | None = None,
    ) -> Comanda:
        exigir_operador_comanda(ator)
        validar_quantidade_item(quantidade)
        observacao = validar_observacao(observacao)
        for pedido in adicionais:
            validar_quantidade_item(pedido.quantidade)
        if len({p.adicional_id for p in adicionais}) != len(adicionais):
            raise ItemComandaInvalido("adicional_repetido")

        try:
            await _travar_comanda_aberta(self._uow, comanda_id)
            item = await self._montar_item(
                produto_id, tamanho_id, quantidade, adicionais, observacao
            )
            salvo = await self._uow.comandas.adicionar_item(comanda_id, item)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "adicionar_item",
                "comanda",
                str(comanda_id),
                {
                    "item_id": salvo.id,
                    "produto_id": produto_id,
                    "tamanho_id": tamanho_id,
                    "quantidade": quantidade,
                    "preco_unitario": str(salvo.preco_unitario),
                    "adicionais": [
                        {
                            "adicional_id": a.adicional_id,
                            "quantidade": a.quantidade,
                            "preco_unitario": str(a.preco_unitario),
                        }
                        for a in salvo.adicionais
                    ],
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()  # solta o lock da comanda
            raise
        return await _recarregar(self._uow, comanda_id)

    async def _montar_item(
        self,
        produto_id: int,
        tamanho_id: int,
        quantidade: int,
        adicionais: Sequence[AdicionalPedido],
        observacao: str | None,
    ) -> ItemComanda:
        cardapio = self._uow.cardapio
        produto = await cardapio.obter_produto(produto_id)
        if produto is None:
            raise ProdutoNaoEncontrado
        tamanho = await cardapio.obter_tamanho(tamanho_id)
        if tamanho is None:
            raise TamanhoNaoEncontrado
        if not produto.ativo:
            raise ItemComandaInvalido("produto_inativo")
        if not tamanho.ativo:
            raise ItemComandaInvalido("tamanho_inativo")
        preco = await cardapio.obter_preco(produto_id, tamanho_id)
        if preco is None:
            raise ItemComandaInvalido("produto_sem_preco")

        congelados: list[AdicionalItem] = []
        for pedido in adicionais:
            adicional = await cardapio.obter_adicional(pedido.adicional_id)
            if adicional is None:
                raise AdicionalNaoEncontrado
            if not adicional.ativo:
                raise ItemComandaInvalido("adicional_inativo")
            congelados.append(
                AdicionalItem(
                    adicional.id_persistido, adicional.nome, adicional.preco, pedido.quantidade
                )
            )
        return ItemComanda(
            produto_id=produto_id,
            tamanho_id=tamanho_id,
            nome_produto=produto.nome,
            nome_tamanho=tamanho.nome,
            preco_unitario=preco.preco,
            quantidade=quantidade,
            observacao=observacao,
            adicionais=congelados,
        )


class AtualizarItem:
    """Altera quantidade e/ou observação de um item (`observacao=""` limpa; None mantém)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        comanda_id: int,
        item_id: int,
        quantidade: int | None = None,
        observacao: str | None = None,
    ) -> Comanda:
        exigir_operador_comanda(ator)
        if quantidade is not None:
            validar_quantidade_item(quantidade)
        nova_observacao = validar_observacao(observacao) if observacao is not None else None
        try:
            comanda = await _travar_comanda_aberta(self._uow, comanda_id)
            atual = next((i for i in comanda.itens if i.id == item_id), None)
            if atual is None:
                raise ItemComandaNaoEncontrado
            await self._uow.comandas.atualizar_item(
                comanda_id,
                item_id,
                atual.quantidade if quantidade is None else quantidade,
                atual.observacao if observacao is None else nova_observacao,
            )
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "atualizar_item",
                "comanda",
                str(comanda_id),
                {
                    "item_id": item_id,
                    "quantidade_antes": atual.quantidade,
                    "quantidade_depois": atual.quantidade if quantidade is None else quantidade,
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return await _recarregar(self._uow, comanda_id)


class RemoverItem:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, comanda_id: int, item_id: int) -> None:
        exigir_operador_comanda(ator)
        try:
            comanda = await _travar_comanda_aberta(self._uow, comanda_id)
            atual = next((i for i in comanda.itens if i.id == item_id), None)
            if atual is None:
                raise ItemComandaNaoEncontrado
            await self._uow.comandas.remover_item(comanda_id, item_id)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "remover_item",
                "comanda",
                str(comanda_id),
                {
                    "item_id": item_id,
                    "produto_id": atual.produto_id,
                    "tamanho_id": atual.tamanho_id,
                    "quantidade": atual.quantidade,
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
