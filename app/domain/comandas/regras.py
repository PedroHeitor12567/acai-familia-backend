"""Regras puras de comandas (sem I/O): totais, consumo de estoque e transições de status."""

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from app.domain.comandas.entities import Comanda, ItemComanda, StatusComanda
from app.domain.estoque.entities import ItemFichaTecnica
from app.domain.estoque.regras import calcular_consumo
from app.domain.exceptions import OperacaoNaoPermitida, ValorInvalido

MAX_CLIENTE_NOME = 120
MAX_CLIENTE_CONTATO = 60
MAX_OBSERVACAO = 500
MAX_QUANTIDADE_ITEM = 99


def validar_cliente_nome(nome: str) -> str:
    """Obrigatório, sem espaços nas pontas, 1 a 120 caracteres."""
    limpo = nome.strip() if isinstance(nome, str) else ""
    if not limpo or len(limpo) > MAX_CLIENTE_NOME:
        raise ValorInvalido("cliente_nome_invalido")
    return limpo


def validar_texto_opcional(texto: str | None, maximo: int, motivo: str) -> str | None:
    """Texto livre opcional: vazio vira None; acima de `maximo` caracteres é erro."""
    if texto is None:
        return None
    limpo = texto.strip()
    if len(limpo) > maximo:
        raise ValorInvalido(motivo)
    return limpo or None


def validar_observacao(texto: str | None) -> str | None:
    return validar_texto_opcional(texto, MAX_OBSERVACAO, "observacao_invalida")


def validar_quantidade_item(quantidade: int) -> int:
    """Inteiro de 1 a 99 (bool não vale)."""
    if (
        not isinstance(quantidade, int)
        or isinstance(quantidade, bool)
        or not 1 <= quantidade <= MAX_QUANTIDADE_ITEM
    ):
        raise ValorInvalido("quantidade_item_invalida")
    return quantidade


def subtotal_item(item: ItemComanda) -> Decimal:
    """(preço + Σ preço do adicional × qtd do adicional) × quantidade do item."""
    adicionais = sum((a.preco_unitario * a.quantidade for a in item.adicionais), start=Decimal("0"))
    return (item.preco_unitario + adicionais) * item.quantidade


def total_comanda(itens: Iterable[ItemComanda]) -> Decimal:
    return sum((subtotal_item(i) for i in itens), start=Decimal("0.00"))


def total_efetivo(comanda: Comanda) -> Decimal:
    """Fechada: o snapshot gravado no fechamento. Demais: calculado dos itens atuais."""
    if comanda.total_fechado is not None:
        return comanda.total_fechado
    return total_comanda(comanda.itens)


def consumo_da_comanda(
    itens: Sequence[ItemComanda],
    fichas_produto: Mapping[tuple[int, int], Sequence[ItemFichaTecnica]],
    fichas_adicional: Mapping[int, Sequence[ItemFichaTecnica]],
) -> dict[int, Decimal]:
    """Consumo da comanda inteira (insumo_id -> quantidade) num único dict.

    Soma o mesmo insumo vindo de itens e adicionais diferentes, para que a baixa seja feita
    uma vez por insumo. Ficha ausente nos mapas conta como "sem ficha" (não consome nada).
    """
    consumo: dict[int, Decimal] = {}

    def somar(parcial: dict[int, Decimal]) -> None:
        for insumo_id, qtd in parcial.items():
            consumo[insumo_id] = consumo.get(insumo_id, Decimal("0")) + qtd

    for item in itens:
        somar(
            calcular_consumo(
                fichas_produto.get((item.produto_id, item.tamanho_id), ()), item.quantidade
            )
        )
        for adicional in item.adicionais:
            ficha = fichas_adicional.get(adicional.adicional_id, ())
            somar(calcular_consumo(ficha, item.quantidade * adicional.quantidade))
    return consumo


def itens_sem_ficha(
    itens: Sequence[ItemComanda],
    fichas_produto: Mapping[tuple[int, int], Sequence[ItemFichaTecnica]],
) -> list[int]:
    """Ids dos itens cujo produto/tamanho não tem ficha técnica (não baixam estoque)."""
    return [i.id_persistido for i in itens if not fichas_produto.get((i.produto_id, i.tamanho_id))]


def exigir_aberta(comanda: Comanda) -> None:
    """Só comanda aberta aceita alterações; fechada e cancelada são estados terminais."""
    if comanda.status is not StatusComanda.ABERTA:
        raise OperacaoNaoPermitida("comanda_nao_aberta")


def validar_fechamento(comanda: Comanda) -> None:
    """`aberta -> fechada`, e só com ao menos um item."""
    exigir_aberta(comanda)
    if not comanda.itens:
        raise OperacaoNaoPermitida("comanda_vazia")


def validar_cancelamento(comanda: Comanda) -> None:
    """`aberta -> cancelada`."""
    exigir_aberta(comanda)
