class DomainError(Exception):
    """Erro base das regras de negócio."""


class CredenciaisInvalidas(DomainError):
    pass


class TokenInvalido(DomainError):
    pass


class PermissaoNegada(DomainError):
    pass


class EmailJaCadastrado(DomainError):
    pass


class UsuarioNaoEncontrado(DomainError):
    pass


class OperacaoNaoPermitida(DomainError):
    """Operação válida em tese, mas proibida pelo estado atual (ex.: último admin)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class SenhaAtualIncorreta(DomainError):
    pass


class MuitasTentativas(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Muitas tentativas de login")
        self.retry_after = retry_after
