from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    CredenciaisInvalidas,
    EmailJaCadastrado,
    EstoqueInsuficiente,
    EstoqueInsuficienteNoFechamento,
    FichaTecnicaInvalida,
    ItemComandaInvalido,
    MuitasTentativas,
    NaoEncontrado,
    NomeJaCadastrado,
    OperacaoNaoPermitida,
    PeriodoInvalido,
    PermissaoNegada,
    RegraInvalida,
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

# Motivos de comanda viram o próprio `code` da resposta (409), para o front reagir a cada um.
_MOTIVOS_COMANDA = {
    "comanda_nao_aberta": "A comanda não está aberta (já foi fechada ou cancelada)",
    "comanda_vazia": "A comanda não tem itens; lance ao menos um item antes de fechar",
}

_MOTIVOS_CAIXA = {
    "caixa_ja_aberto": "Já existe uma sessão de caixa aberta",
    "caixa_fechado": "Não há caixa aberto; abra o caixa antes de fechar a comanda",
    "sessao_nao_aberta": "A sessão de caixa não está aberta",
    "saldo_caixa_insuficiente": "A retirada deixaria o saldo em dinheiro do caixa negativo",
    "lancamento_nao_pendente": "O lançamento não está pendente (já foi baixado ou cancelado)",
    "categoria_financeira_inativa": "A categoria financeira está inativa",
}

_MOTIVOS_REGRA = {
    "pagamento_diferente_do_total": "Os pagamentos devem somar exatamente o total da comanda",
    "forma_repetida": "A mesma forma de pagamento aparece mais de uma vez",
    "valor_recebido_invalido": "valor_recebido só vale para dinheiro, com até 2 casas decimais",
    "valor_recebido_insuficiente": "O valor recebido em dinheiro é menor que o valor pago",
    "justificativa_obrigatoria": "Informe a observação: a contagem difere do valor esperado",
    "categoria_incompativel": "A categoria não combina com o tipo do lançamento "
    "(pagar usa despesa; receber usa receita)",
}

_MOTIVOS_VALOR = {
    "pagamento_valor_invalido": "Valor de pagamento inválido: use valor > 0 com até 2 casas",
    "motivo_movimento_invalido": "Motivo inválido: informe de 1 a 255 caracteres",
    "nome_categoria_financeira_invalido": "Nome inválido: use de 1 a 80 caracteres",
    "descricao_invalida": "Descrição inválida: use de 1 a 160 caracteres",
    "contraparte_invalida": "Contraparte inválida: use até 120 caracteres",
    "cliente_nome_invalido": "Nome do cliente inválido: use de 1 a 120 caracteres",
    "cliente_contato_invalido": "Contato inválido: use até 60 caracteres",
    "observacao_invalida": "Observação inválida: use até 500 caracteres",
    "motivo_invalido": "Motivo inválido: use até 255 caracteres",
    "quantidade_item_invalida": "Quantidade inválida: use um número inteiro de 1 a 99",
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

_MOTIVOS_ITEM = {
    "produto_inativo": "O produto está inativo",
    "tamanho_inativo": "O tamanho está inativo",
    "adicional_inativo": "O adicional está inativo",
    "produto_sem_preco": "O produto não tem preço definido para este tamanho",
    "adicional_repetido": "O mesmo adicional aparece mais de uma vez no item",
}

_MOTIVOS_PERIODO = {
    "periodo_invertido": "A data inicial (de) não pode ser depois da final (ate)",
    "periodo_no_futuro": "A data final (ate) não pode ser depois de hoje",
    "periodo_longo_demais": "O período não pode passar de 366 dias",
    "agrupamento_dia_longo_demais": "Agrupar por dia só vale para períodos de até 92 dias; "
    "use semana ou mes",
}

_ENTIDADES = {
    "categoria": "Já existe uma categoria com este nome",
    "tamanho": "Já existe um tamanho com este nome",
    "adicional": "Já existe um adicional com este nome",
    "insumo": "Já existe um insumo com este nome",
    "produto": "Já existe um produto com este nome nesta categoria",
    "categoria_financeira": "Já existe uma categoria financeira com este nome neste tipo",
}


def _resp(
    status: int,
    code: str,
    msg: str,
    headers: dict[str, str] | None = None,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    """Formato único de erro: `code` estável para o front, `detail` em português.
    `extra` acrescenta campos de contexto (ex.: qual insumo faltou)."""
    return JSONResponse(
        status_code=status, content={"code": code, "detail": msg, **(extra or {})}, headers=headers
    )


def _texto_estoque_insuficiente(exc: EstoqueInsuficiente) -> str:
    quem = f" de {exc.insumo_nome}" if exc.insumo_nome else ""
    return f"Estoque insuficiente{quem}: disponível {exc.disponivel}, solicitado {exc.solicitado}"


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
        if exc.motivo in _MOTIVOS_COMANDA:
            return _resp(409, exc.motivo, _MOTIVOS_COMANDA[exc.motivo])
        if exc.motivo in _MOTIVOS_CAIXA:
            return _resp(409, exc.motivo, _MOTIVOS_CAIXA[exc.motivo])
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
        return _resp(422, "estoque_insuficiente", _texto_estoque_insuficiente(exc))

    @app.exception_handler(EstoqueInsuficienteNoFechamento)
    async def _estoque_insuficiente_no_fechamento(
        _: Request, exc: EstoqueInsuficienteNoFechamento
    ) -> JSONResponse:
        # Conflito com o estado do estoque: a comanda continua aberta e nada foi baixado.
        return _resp(
            409,
            "estoque_insuficiente",
            _texto_estoque_insuficiente(exc),
            extra={
                "insumo_id": exc.insumo_id,
                "insumo_nome": exc.insumo_nome,
                "disponivel": str(exc.disponivel),
                "solicitado": str(exc.solicitado),
            },
        )

    @app.exception_handler(FichaTecnicaInvalida)
    async def _ficha_invalida(_: Request, exc: FichaTecnicaInvalida) -> JSONResponse:
        return _resp(
            422,
            "ficha_tecnica_invalida",
            _MOTIVOS_FICHA.get(exc.motivo, "Ficha técnica inválida"),
        )

    @app.exception_handler(ItemComandaInvalido)
    async def _item_invalido(_: Request, exc: ItemComandaInvalido) -> JSONResponse:
        return _resp(422, exc.motivo, _MOTIVOS_ITEM.get(exc.motivo, "Item inválido"))

    @app.exception_handler(RegraInvalida)
    async def _regra_invalida(_: Request, exc: RegraInvalida) -> JSONResponse:
        return _resp(422, exc.motivo, _MOTIVOS_REGRA.get(exc.motivo, "Dados inválidos"))

    @app.exception_handler(PeriodoInvalido)
    async def _periodo_invalido(_: Request, exc: PeriodoInvalido) -> JSONResponse:
        return _resp(
            422,
            "periodo_invalido",
            _MOTIVOS_PERIODO.get(exc.motivo, "Período inválido"),
            extra={"motivo": exc.motivo},
        )
