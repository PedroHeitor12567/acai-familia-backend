from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    CredenciaisInvalidas,
    EmailJaCadastrado,
    MuitasTentativas,
    OperacaoNaoPermitida,
    PermissaoNegada,
    SenhaAtualIncorreta,
    TokenInvalido,
    UsuarioNaoEncontrado,
)

_MOTIVOS_OPERACAO = {
    "ultimo_admin": "Deve existir ao menos um administrador ativo",
    "auto_desativacao": "Você não pode desativar a si mesmo; peça a outro administrador",
    "auto_rebaixamento": "Você não pode rebaixar o próprio papel; peça a outro administrador",
    "senha_igual_a_atual": "A nova senha deve ser diferente da atual",
}


def _resp(status: int, code: str, msg: str, headers: dict[str, str] | None = None) -> JSONResponse:
    """Formato único de erro: `code` estável para o front, `detail` em português."""
    return JSONResponse(status_code=status, content={"code": code, "detail": msg}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CredenciaisInvalidas)
    async def _cred(_: Request, __: CredenciaisInvalidas) -> JSONResponse:
        return _resp(401, "credenciais_invalidas", "Credenciais inválidas")

    @app.exception_handler(TokenInvalido)
    async def _tok(_: Request, __: TokenInvalido) -> JSONResponse:
        return _resp(
            401, "token_invalido", "Token inválido ou expirado", {"WWW-Authenticate": "Bearer"}
        )

    @app.exception_handler(PermissaoNegada)
    async def _perm(_: Request, __: PermissaoNegada) -> JSONResponse:
        return _resp(403, "permissao_negada", "Sem permissão para esta ação")

    @app.exception_handler(EmailJaCadastrado)
    async def _email(_: Request, __: EmailJaCadastrado) -> JSONResponse:
        return _resp(409, "email_ja_cadastrado", "E-mail já cadastrado")

    @app.exception_handler(MuitasTentativas)
    async def _rate(_: Request, exc: MuitasTentativas) -> JSONResponse:
        return _resp(
            429,
            "muitas_tentativas",
            "Muitas tentativas. Tente novamente mais tarde.",
            {"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(UsuarioNaoEncontrado)
    async def _nao_encontrado(_: Request, __: UsuarioNaoEncontrado) -> JSONResponse:
        return _resp(404, "usuario_nao_encontrado", "Usuário não encontrado")

    @app.exception_handler(OperacaoNaoPermitida)
    async def _operacao(_: Request, exc: OperacaoNaoPermitida) -> JSONResponse:
        return _resp(
            409,
            "operacao_nao_permitida",
            _MOTIVOS_OPERACAO.get(exc.motivo, "Operação não permitida"),
        )

    @app.exception_handler(SenhaAtualIncorreta)
    async def _senha_atual(_: Request, __: SenhaAtualIncorreta) -> JSONResponse:
        return _resp(400, "senha_atual_incorreta", "Senha atual incorreta")
