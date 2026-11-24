from fastapi import APIRouter, Request, Response, status

from app.interfaces.http.deps import (
    AlterarPropriaSenhaDep,
    AutenticarUsuarioDep,
    CurrentUser,
    RenovarTokenDep,
)
from app.interfaces.http.schemas.auth import LoginIn, RefreshIn, TokenOut
from app.interfaces.http.schemas.usuarios import AlterarSenhaIn, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, caso: AutenticarUsuarioDep) -> TokenOut:
    origem = request.client.host if request.client else "desconhecido"
    par = caso.executar(body.email, body.senha, origem)
    return TokenOut(access_token=par.access_token, refresh_token=par.refresh_token)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, caso: RenovarTokenDep) -> TokenOut:
    par = caso.executar(body.refresh_token)
    return TokenOut(access_token=par.access_token, refresh_token=par.refresh_token)


@router.get("/me", response_model=UsuarioOut)
def me(usuario: CurrentUser) -> UsuarioOut:
    return UsuarioOut.de_entidade(usuario)


@router.post("/alterar-senha", status_code=status.HTTP_204_NO_CONTENT)
def alterar_senha(
    body: AlterarSenhaIn, usuario: CurrentUser, caso: AlterarPropriaSenhaDep
) -> Response:
    caso.executar(usuario, body.senha_atual, body.nova_senha)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
