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
async def login(body: LoginIn, request: Request, caso: AutenticarUsuarioDep) -> TokenOut:
    origem = request.client.host if request.client else "desconhecido"
    par = await caso.executar(body.email, body.senha, origem)
    return TokenOut(access_token=par.access_token, refresh_token=par.refresh_token)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, caso: RenovarTokenDep) -> TokenOut:
    par = await caso.executar(body.refresh_token)
    return TokenOut(access_token=par.access_token, refresh_token=par.refresh_token)


@router.get("/me", response_model=UsuarioOut)
async def me(usuario: CurrentUser) -> UsuarioOut:
    return UsuarioOut.de_entidade(usuario)


@router.post("/alterar-senha", status_code=status.HTTP_204_NO_CONTENT)
async def alterar_senha(
    body: AlterarSenhaIn, usuario: CurrentUser, caso: AlterarPropriaSenhaDep
) -> Response:
    await caso.executar(usuario, body.senha_atual, body.nova_senha)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
