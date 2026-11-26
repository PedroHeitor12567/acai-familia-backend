from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.cardapio.entities import Tamanho
from app.domain.exceptions import NomeJaCadastrado, TamanhoNaoEncontrado
from app.domain.usuarios.entities import Usuario


class CriarTamanho:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, nome: str) -> Tamanho:
        exigir_gestor(ator)
        if await self._uow.cardapio.obter_tamanho_por_nome(nome) is not None:
            raise NomeJaCadastrado("tamanho")
        tamanho = await self._uow.cardapio.adicionar_tamanho(Tamanho(nome=nome))
        await self._uow.auditoria.registrar(
            ator.id_persistido, "criar", "tamanho", str(tamanho.id), {"nome": nome}
        )
        await self._uow.commit()
        return tamanho


class AtualizarTamanho:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, tamanho_id: int, nome: str | None) -> Tamanho:
        exigir_gestor(ator)
        tamanho = await self._uow.cardapio.obter_tamanho(tamanho_id)
        if tamanho is None:
            raise TamanhoNaoEncontrado
        if nome is None or nome == tamanho.nome:
            return tamanho
        existente = await self._uow.cardapio.obter_tamanho_por_nome(nome)
        if existente is not None and existente.id != tamanho.id:
            raise NomeJaCadastrado("tamanho")
        antes, tamanho.nome = tamanho.nome, nome
        atualizado = await self._uow.cardapio.atualizar_tamanho(tamanho)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "atualizar",
            "tamanho",
            str(tamanho_id),
            {"nome": {"antes": antes, "depois": nome}},
        )
        await self._uow.commit()
        return atualizado


class AlterarStatusTamanho:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, tamanho_id: int, ativo: bool) -> Tamanho:
        exigir_gestor(ator)
        tamanho = await self._uow.cardapio.obter_tamanho(tamanho_id)
        if tamanho is None:
            raise TamanhoNaoEncontrado
        if tamanho.ativo == ativo:
            return tamanho
        tamanho.ativo = ativo
        atualizado = await self._uow.cardapio.atualizar_tamanho(tamanho)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "ativar" if ativo else "desativar",
            "tamanho",
            str(tamanho_id),
            {"ativo": {"antes": not ativo, "depois": ativo}},
        )
        await self._uow.commit()
        return atualizado


class ListarTamanhos:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Tamanho], int]:
        return await self._uow.cardapio.listar_tamanhos(ativo, limit, offset)
