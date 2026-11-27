from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import CategoriaFinanceiraNaoEncontrada, NomeJaCadastrado
from app.domain.financeiro.entities import CategoriaFinanceira, TipoCategoria
from app.domain.financeiro.regras import validar_nome_categoria
from app.domain.usuarios.entities import Usuario


class CriarCategoriaFinanceira:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, nome: str, tipo: TipoCategoria) -> CategoriaFinanceira:
        exigir_gestor(ator)
        nome = validar_nome_categoria(nome)
        try:
            if await self._uow.financeiro.obter_categoria_por_nome(nome, tipo) is not None:
                raise NomeJaCadastrado("categoria_financeira")
            categoria = await self._uow.financeiro.adicionar_categoria(
                CategoriaFinanceira(nome=nome, tipo=tipo)
            )
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "criar",
                "categoria_financeira",
                str(categoria.id),
                {"nome": nome, "tipo": str(tipo)},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return categoria


class AtualizarCategoriaFinanceira:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        categoria_id: int,
        nome: str | None = None,
        ativo: bool | None = None,
    ) -> CategoriaFinanceira:
        exigir_gestor(ator)
        if nome is not None:
            nome = validar_nome_categoria(nome)
        try:
            categoria = await self._uow.financeiro.obter_categoria(categoria_id)
            if categoria is None:
                raise CategoriaFinanceiraNaoEncontrada
            mudancas: dict[str, object] = {}
            if nome is not None and nome != categoria.nome:
                existente = await self._uow.financeiro.obter_categoria_por_nome(
                    nome, categoria.tipo
                )
                if existente is not None and existente.id != categoria.id:
                    raise NomeJaCadastrado("categoria_financeira")
                mudancas["nome"] = {"antes": categoria.nome, "depois": nome}
                categoria.nome = nome
            if ativo is not None and ativo != categoria.ativo:
                mudancas["ativo"] = {"antes": categoria.ativo, "depois": ativo}
                categoria.ativo = ativo
            if not mudancas:
                return categoria
            atualizada = await self._uow.financeiro.atualizar_categoria(categoria)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "atualizar",
                "categoria_financeira",
                str(categoria_id),
                mudancas,
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return atualizada


class ListarCategoriasFinanceiras:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, tipo: TipoCategoria | None = None, ativo: bool | None = None
    ) -> list[CategoriaFinanceira]:
        exigir_gestor(ator)
        return await self._uow.financeiro.listar_categorias(tipo, ativo)
