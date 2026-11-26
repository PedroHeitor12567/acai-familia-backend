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


class NaoEncontrado(DomainError):
    """Base dos 404 do cardápio/estoque. Cada subclasse define o `code` estável e a mensagem."""

    code = "nao_encontrado"
    mensagem = "Recurso não encontrado"


class CategoriaNaoEncontrada(NaoEncontrado):
    code = "categoria_nao_encontrada"
    mensagem = "Categoria não encontrada"


class ProdutoNaoEncontrado(NaoEncontrado):
    code = "produto_nao_encontrado"
    mensagem = "Produto não encontrado"


class TamanhoNaoEncontrado(NaoEncontrado):
    code = "tamanho_nao_encontrado"
    mensagem = "Tamanho não encontrado"


class AdicionalNaoEncontrado(NaoEncontrado):
    code = "adicional_nao_encontrado"
    mensagem = "Adicional não encontrado"


class InsumoNaoEncontrado(NaoEncontrado):
    code = "insumo_nao_encontrado"
    mensagem = "Insumo não encontrado"


class NomeJaCadastrado(DomainError):
    """Nome duplicado (categoria, tamanho, adicional, insumo ou produto na mesma categoria)."""

    def __init__(self, entidade: str) -> None:
        super().__init__(entidade)
        self.entidade = entidade


class ValorInvalido(DomainError):
    """Valor que viola uma regra de domínio (preço negativo, quantidade <= 0...)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class EstoqueInsuficiente(DomainError):
    def __init__(self, disponivel: object, solicitado: object) -> None:
        super().__init__(f"disponível {disponivel}, solicitado {solicitado}")
        self.disponivel = disponivel
        self.solicitado = solicitado


class FichaTecnicaInvalida(DomainError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class MuitasTentativas(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Muitas tentativas de login")
        self.retry_after = retry_after
