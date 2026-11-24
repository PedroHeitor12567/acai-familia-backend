from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.usuarios.ports import FiltrosUsuario
from app.domain.usuarios.entities import Papel, Usuario
from app.interfaces.http.deps import (
    AlterarStatusUsuarioDep,
    AtualizarUsuarioDep,
    CriarUsuarioDep,
    ListarUsuariosDep,
    ObterUsuarioDep,
    RedefinirSenhaDep,
    require_roles,
)
from app.interfaces.http.schemas.usuarios import (
    PaginaUsuariosOut,
    RedefinirSenhaIn,
    UsuarioCreateIn,
    UsuarioOut,
    UsuarioUpdateIn,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

AdminDep = Annotated[Usuario, Depends(require_roles(Papel.ADMIN))]
GestorDep = Annotated[Usuario, Depends(require_roles(Papel.ADMIN, Papel.GERENTE))]


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(body: UsuarioCreateIn, admin: AdminDep, caso: CriarUsuarioDep) -> UsuarioOut:
    novo = caso.executar(admin, body.nome, body.email, body.senha, body.papel)
    return UsuarioOut.de_entidade(novo)


@router.get("", response_model=PaginaUsuariosOut)
def listar_usuarios(
    ator: GestorDep,
    caso: ListarUsuariosDep,
    ativo: bool | None = None,
    papel: Papel | None = None,
    q: Annotated[str | None, Query(max_length=120, description="Busca em nome ou e-mail")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginaUsuariosOut:
    itens, total = caso.executar(ator, FiltrosUsuario(ativo=ativo, papel=papel, q=q), limit, offset)
    return PaginaUsuariosOut(
        itens=[UsuarioOut.de_entidade(u) for u in itens], total=total, limit=limit, offset=offset
    )


@router.get("/{usuario_id}", response_model=UsuarioOut)
def obter_usuario(usuario_id: int, ator: GestorDep, caso: ObterUsuarioDep) -> UsuarioOut:
    return UsuarioOut.de_entidade(caso.executar(ator, usuario_id))


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def atualizar_usuario(
    usuario_id: int, body: UsuarioUpdateIn, admin: AdminDep, caso: AtualizarUsuarioDep
) -> UsuarioOut:
    atualizado = caso.executar(admin, usuario_id, body.nome, body.email, body.papel)
    return UsuarioOut.de_entidade(atualizado)


@router.post("/{usuario_id}/desativar", response_model=UsuarioOut)
def desativar_usuario(
    usuario_id: int, admin: AdminDep, caso: AlterarStatusUsuarioDep
) -> UsuarioOut:
    return UsuarioOut.de_entidade(caso.executar(admin, usuario_id, ativo=False))


@router.post("/{usuario_id}/reativar", response_model=UsuarioOut)
def reativar_usuario(usuario_id: int, admin: AdminDep, caso: AlterarStatusUsuarioDep) -> UsuarioOut:
    return UsuarioOut.de_entidade(caso.executar(admin, usuario_id, ativo=True))


@router.post("/{usuario_id}/redefinir-senha", status_code=status.HTTP_204_NO_CONTENT)
def redefinir_senha(
    usuario_id: int, body: RedefinirSenhaIn, admin: AdminDep, caso: RedefinirSenhaDep
) -> Response:
    caso.executar(admin, usuario_id, body.nova_senha)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
