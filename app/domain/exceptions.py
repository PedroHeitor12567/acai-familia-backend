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


class ComandaNaoEncontrada(NaoEncontrado):
    code = "comanda_nao_encontrada"
    mensagem = "Comanda não encontrada"


class ItemComandaNaoEncontrado(NaoEncontrado):
    code = "item_comanda_nao_encontrado"
    mensagem = "Item da comanda não encontrado"


class SessaoCaixaNaoEncontrada(NaoEncontrado):
    code = "sessao_caixa_nao_encontrada"
    mensagem = "Sessão de caixa não encontrada"


class NenhumaSessaoAberta(NaoEncontrado):
    code = "nenhuma_sessao_aberta"
    mensagem = "Não há sessão de caixa aberta"


class CategoriaFinanceiraNaoEncontrada(NaoEncontrado):
    code = "categoria_financeira_nao_encontrada"
    mensagem = "Categoria financeira não encontrada"


class LancamentoNaoEncontrado(NaoEncontrado):
    code = "lancamento_nao_encontrado"
    mensagem = "Lançamento não encontrado"


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
    """Saldo menor que o pedido. `insumo_id`/`insumo_nome` dizem qual insumo faltou (quando
    quem levanta sabe); os usos antigos, sem eles, continuam válidos."""

    def __init__(
        self,
        disponivel: object,
        solicitado: object,
        insumo_id: int | None = None,
        insumo_nome: str | None = None,
    ) -> None:
        super().__init__(f"disponível {disponivel}, solicitado {solicitado}")
        self.disponivel = disponivel
        self.solicitado = solicitado
        self.insumo_id = insumo_id
        self.insumo_nome = insumo_nome


class EstoqueInsuficienteNoFechamento(EstoqueInsuficiente):
    """Falta de insumo ao fechar uma comanda: conflito com o estado do estoque (HTTP 409)."""


class ItemComandaInvalido(DomainError):
    """Item que não pode ser lançado (produto/tamanho/adicional inativo, sem preço...)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class RegraInvalida(DomainError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class PagamentoInvalido(RegraInvalida): ...


class CaixaInvalido(RegraInvalida): ...


class LancamentoInvalido(RegraInvalida): ...


class FichaTecnicaInvalida(DomainError):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class MuitasTentativas(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Muitas tentativas de login")
        self.retry_after = retry_after


class PeriodoInvalido(DomainError):
    """Período de consulta do dashboard fora das regras (`motivo` diz qual)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo
