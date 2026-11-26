from decimal import Decimal
from typing import Any

from app.application.estoque.ports import FiltrosInsumo
from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.estoque.entities import Insumo, UnidadeMedida, validar_quantidade
from app.domain.exceptions import InsumoNaoEncontrado, NomeJaCadastrado
from app.domain.usuarios.entities import Usuario


class CriarInsumo:
    """O saldo nasce em zero: o estoque inicial entra como uma movimentação de entrada,
    para o histórico explicar todo o saldo."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, nome: str, unidade: UnidadeMedida, estoque_minimo: Decimal
    ) -> Insumo:
        exigir_gestor(ator)
        novo = Insumo(nome=nome, unidade=unidade, estoque_minimo=estoque_minimo)  # valida
        if await self._uow.estoque.obter_insumo_por_nome(nome) is not None:
            raise NomeJaCadastrado("insumo")
        insumo = await self._uow.estoque.adicionar_insumo(novo)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "criar",
            "insumo",
            str(insumo.id),
            {"nome": nome, "unidade": str(unidade), "estoque_minimo": str(estoque_minimo)},
        )
        await self._uow.commit()
        return insumo


class AtualizarInsumo:
    """Nome e estoque mínimo. A unidade não muda: o histórico perderia o sentido."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        insumo_id: int,
        nome: str | None = None,
        estoque_minimo: Decimal | None = None,
    ) -> Insumo:
        exigir_gestor(ator)
        insumo = await self._uow.estoque.obter_insumo(insumo_id)
        if insumo is None:
            raise InsumoNaoEncontrado
        if estoque_minimo is not None:
            validar_quantidade(estoque_minimo, permite_zero=True)
        if nome is not None and nome != insumo.nome:
            existente = await self._uow.estoque.obter_insumo_por_nome(nome)
            if existente is not None and existente.id != insumo.id:
                raise NomeJaCadastrado("insumo")

        diff: dict[str, Any] = {}
        for campo, novo in (("nome", nome), ("estoque_minimo", estoque_minimo)):
            antes = getattr(insumo, campo)
            if novo is not None and novo != antes:
                diff[campo] = {"antes": str(antes), "depois": str(novo)}
                setattr(insumo, campo, novo)
        if not diff:
            return insumo

        atualizado = await self._uow.estoque.atualizar_insumo(insumo)
        await self._uow.auditoria.registrar(
            ator.id_persistido, "atualizar", "insumo", str(insumo_id), diff
        )
        await self._uow.commit()
        return atualizado


class AlterarStatusInsumo:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, insumo_id: int, ativo: bool) -> Insumo:
        exigir_gestor(ator)
        insumo = await self._uow.estoque.obter_insumo(insumo_id)
        if insumo is None:
            raise InsumoNaoEncontrado
        if insumo.ativo == ativo:
            return insumo
        insumo.ativo = ativo
        atualizado = await self._uow.estoque.atualizar_insumo(insumo)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "ativar" if ativo else "desativar",
            "insumo",
            str(insumo_id),
            {"ativo": {"antes": not ativo, "depois": ativo}},
        )
        await self._uow.commit()
        return atualizado


class ObterInsumo:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, insumo_id: int) -> Insumo:
        exigir_gestor(ator)
        insumo = await self._uow.estoque.obter_insumo(insumo_id)
        if insumo is None:
            raise InsumoNaoEncontrado
        return insumo


class ListarInsumos:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, filtros: FiltrosInsumo, limit: int, offset: int
    ) -> tuple[list[Insumo], int]:
        exigir_gestor(ator)
        return await self._uow.estoque.listar_insumos(filtros, limit, offset)


class ListarAlertasEstoque:
    """Insumos ativos com saldo <= mínimo. Notificação ativa (push/WhatsApp) não faz parte."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, limit: int, offset: int) -> tuple[list[Insumo], int]:
        exigir_gestor(ator)
        return await self._uow.estoque.listar_insumos(
            FiltrosInsumo(ativo=True, abaixo_do_minimo=True), limit, offset
        )
