from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    CredenciaisInvalidas,
    EmailJaCadastrado,
    EstoqueInsuficiente,
    FichaTecnicaInvalida,
    MuitasTentativas,
    NaoEncontrado,
    NomeJaCadastrado,
    OperacaoNaoPermitida,
    PermissaoNegada,
    SenhaAtualIncorreta,
    TokenInvalido,
    UsuarioNaoEncontrado,
    ValorInvalido,
)

_MOTIVOS_OPERACAO = {
    "ultimo_admin": "Deve existir ao menos um administrador ativo",
    "auto_desativacao": "Você não pode desativar a si mesmo; peça a outro administrador",
    "auto_rebaixamento": "Você não pode rebaixar o próprio papel; peça a outro administrador",
    "senha_igual_a_atual": "A nova senha deve ser diferente da atual",
    "categoria_inativa": "A categoria está inativa",
    "tamanho_inativo": "O tamanho está inativo",
    "insumo_inativo": "O insumo está inativo",
}

_MOTIVOS_VALOR = {
    "preco_invalido": "Preço inválido: use valor >= 0 com até 2 casas decimais",
    "quantidade_invalida": "Quantidade inválida: use valor > 0 com até 3 casas decimais",
    "ajuste_sem_diferenca": "A contagem informada é igual ao saldo atual; nada a ajustar",
}

_MOTIVOS_FICHA = {
    "insumo_repetido": "O mesmo insumo aparece mais de uma vez na ficha técnica",
    "insumo_inexistente": "A ficha técnica referencia um insumo que não existe",
    "insumo_inativo": "A ficha técnica referencia um insumo inativo",
    "produto_inativo": "O produto está inativo",
    "adicional_inativo": "O adicional está inativo",
    "produto_sem_tamanho": "O produto não tem preço definido para este tamanho",
}

_ENTIDADES = {
    "categoria": "Já existe uma categoria com este nome",
    "tamanho": "Já existe um tamanho com este nome",
    "adicional": "Já existe um adicional com este nome",
    "insumo": "Já existe um insumo com este nome",
    "produto": "Já existe um produto com este nome nesta categoria",
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

    @app.exception_handler(NaoEncontrado)
    async def _recurso_nao_encontrado(_: Request, exc: NaoEncontrado) -> JSONResponse:
        return _resp(404, exc.code, exc.mensagem)

    @app.exception_handler(NomeJaCadastrado)
    async def _nome_duplicado(_: Request, exc: NomeJaCadastrado) -> JSONResponse:
        return _resp(409, "nome_ja_cadastrado", _ENTIDADES.get(exc.entidade, "Nome já cadastrado"))

    @app.exception_handler(ValorInvalido)
    async def _valor_invalido(_: Request, exc: ValorInvalido) -> JSONResponse:
        return _resp(422, "valor_invalido", _MOTIVOS_VALOR.get(exc.motivo, "Valor inválido"))

    @app.exception_handler(EstoqueInsuficiente)
    async def _estoque_insuficiente(_: Request, exc: EstoqueInsuficiente) -> JSONResponse:
        return _resp(
            422,
            "estoque_insuficiente",
            f"Estoque insuficiente: disponível {exc.disponivel}, solicitado {exc.solicitado}",
        )

    @app.exception_handler(FichaTecnicaInvalida)
    async def _ficha_invalida(_: Request, exc: FichaTecnicaInvalida) -> JSONResponse:
        return _resp(
            422,
            "ficha_tecnica_invalida",
            _MOTIVOS_FICHA.get(exc.motivo, "Ficha técnica inválida"),
        )
