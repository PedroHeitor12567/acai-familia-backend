from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.usuarios.use_cases.autenticar_usuario import AutenticarUsuario
from app.application.usuarios.use_cases.criar_usuario import CriarUsuario
from app.application.usuarios.use_cases.renovar_token import RenovarToken
from app.bootstrap.container import (
    TokensDep,
    UowDep,
    get_autenticar_usuario,
    get_criar_usuario,
    get_renovar_token,
)
from app.domain.exceptions import PermissaoNegada, TokenInvalido
from app.domain.usuarios.entities import Papel, Usuario

_bearer = HTTPBearer(auto_error=False)

AutenticarUsuarioDep = Annotated[AutenticarUsuario, Depends(get_autenticar_usuario)]
RenovarTokenDep = Annotated[RenovarToken, Depends(get_renovar_token)]
CriarUsuarioDep = Annotated[CriarUsuario, Depends(get_criar_usuario)]


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    tokens: TokensDep,
    uow: UowDep,
) -> Usuario:
    if creds is None:
        raise TokenInvalido
    claims = tokens.decodificar(creds.credentials, "access")
    usuario = uow.usuarios.obter_por_id(claims.usuario_id)
    if usuario is None or not usuario.ativo:
        raise TokenInvalido
    return usuario


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require_roles(*papeis: Papel) -> Callable[[Usuario], Usuario]:
    """Barreira de borda (HTTP). A regra de quem pode o quê também é checada no caso de uso."""

    def checker(usuario: CurrentUser) -> Usuario:
        if usuario.papel not in papeis:
            raise PermissaoNegada
        return usuario

    return checker
