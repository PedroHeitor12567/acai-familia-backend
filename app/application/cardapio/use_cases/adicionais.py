from decimal import Decimal
from typing import Any

from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.cardapio.entities import Adicional, validar_preco
from app.domain.exceptions import AdicionalNaoEncontrado, NomeJaCadastrado
from app.domain.usuarios.entities import Usuario


class CriarAdicional:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, nome: str, preco: Decimal) -> Adicional:
        exigir_gestor(ator)
        if await self._uow.cardapio.obter_adicional_por_nome(nome) is not None:
            raise NomeJaCadastrado("adicional")
        adicional = await self._uow.cardapio.adicionar_adicional(Adicional(nome=nome, preco=preco))
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "criar",
            "adicional",
            str(adicional.id),
            {"nome": nome, "preco": str(preco)},
        )
        await self._uow.commit()
        return adicional


class AtualizarAdicional:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        adicional_id: int,
        nome: str | None = None,
        preco: Decimal | None = None,
    ) -> Adicional:
        exigir_gestor(ator)
        adicional = await self._uow.cardapio.obter_adicional(adicional_id)
        if adicional is None:
            raise AdicionalNaoEncontrado
        if preco is not None:
            validar_preco(preco)
        if nome is not None and nome != adicional.nome:
            existente = await self._uow.cardapio.obter_adicional_por_nome(nome)
            if existente is not None and existente.id != adicional.id:
                raise NomeJaCadastrado("adicional")

        diff: dict[str, Any] = {}
        for campo, novo in (("nome", nome), ("preco", preco)):
            antes = getattr(adicional, campo)
            if novo is not None and novo != antes:
                diff[campo] = {"antes": str(antes), "depois": str(novo)}
                setattr(adicional, campo, novo)
        if not diff:
            return adicional

        atualizado = await self._uow.cardapio.atualizar_adicional(adicional)
        await self._uow.auditoria.registrar(
            ator.id_persistido, "atualizar", "adicional", str(adicional_id), diff
        )
        await self._uow.commit()
        return atualizado


class AlterarStatusAdicional:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, adicional_id: int, ativo: bool) -> Adicional:
        exigir_gestor(ator)
        adicional = await self._uow.cardapio.obter_adicional(adicional_id)
        if adicional is None:
            raise AdicionalNaoEncontrado
        if adicional.ativo == ativo:
            return adicional
        adicional.ativo = ativo
        atualizado = await self._uow.cardapio.atualizar_adicional(adicional)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "ativar" if ativo else "desativar",
            "adicional",
            str(adicional_id),
            {"ativo": {"antes": not ativo, "depois": ativo}},
        )
        await self._uow.commit()
        return atualizado


class ListarAdicionais:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Adicional], int]:
        return await self._uow.cardapio.listar_adicionais(ativo, limit, offset)
