from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.cardapio.entities import Categoria
from app.domain.exceptions import CategoriaNaoEncontrada, NomeJaCadastrado
from app.domain.usuarios.entities import Usuario


class CriarCategoria:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, nome: str) -> Categoria:
        exigir_gestor(ator)
        if await self._uow.cardapio.obter_categoria_por_nome(nome) is not None:
            raise NomeJaCadastrado("categoria")
        categoria = await self._uow.cardapio.adicionar_categoria(Categoria(nome=nome))
        await self._uow.auditoria.registrar(
            ator.id_persistido, "criar", "categoria", str(categoria.id), {"nome": nome}
        )
        await self._uow.commit()
        return categoria


class AtualizarCategoria:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, categoria_id: int, nome: str | None) -> Categoria:
        exigir_gestor(ator)
        categoria = await self._uow.cardapio.obter_categoria(categoria_id)
        if categoria is None:
            raise CategoriaNaoEncontrada
        if nome is None or nome == categoria.nome:
            return categoria
        existente = await self._uow.cardapio.obter_categoria_por_nome(nome)
        if existente is not None and existente.id != categoria.id:
            raise NomeJaCadastrado("categoria")
        antes, categoria.nome = categoria.nome, nome
        atualizada = await self._uow.cardapio.atualizar_categoria(categoria)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "atualizar",
            "categoria",
            str(categoria_id),
            {"nome": {"antes": antes, "depois": nome}},
        )
        await self._uow.commit()
        return atualizada


class AlterarStatusCategoria:
    """Soft delete: categoria inativa continua referenciável por produtos e comandas antigas."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, categoria_id: int, ativo: bool) -> Categoria:
        exigir_gestor(ator)
        categoria = await self._uow.cardapio.obter_categoria(categoria_id)
        if categoria is None:
            raise CategoriaNaoEncontrada
        if categoria.ativo == ativo:
            return categoria
        categoria.ativo = ativo
        atualizada = await self._uow.cardapio.atualizar_categoria(categoria)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "ativar" if ativo else "desativar",
            "categoria",
            str(categoria_id),
            {"ativo": {"antes": not ativo, "depois": ativo}},
        )
        await self._uow.commit()
        return atualizada


class ObterCategoria:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, categoria_id: int) -> Categoria:
        categoria = await self._uow.cardapio.obter_categoria(categoria_id)
        if categoria is None:
            raise CategoriaNaoEncontrada
        return categoria


class ListarCategorias:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ativo: bool | None, limit: int, offset: int
    ) -> tuple[list[Categoria], int]:
        return await self._uow.cardapio.listar_categorias(ativo, limit, offset)
