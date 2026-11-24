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


class MuitasTentativas(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Muitas tentativas de login")
        self.retry_after = retry_after
