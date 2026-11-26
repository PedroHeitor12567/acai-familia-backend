from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.shared import ComId


class OrigemComanda(StrEnum):
    BALCAO = "balcao"
    WHATSAPP = "whatsapp"


class StatusComanda(StrEnum):
    ABERTA = "aberta"
    FECHADA = "fechada"
    CANCELADA = "cancelada"


@dataclass(frozen=True)
class AdicionalItem:
    """Adicional lançado num item. Nome e preço são snapshots do momento do lançamento."""

    adicional_id: int
    nome: str
    preco_unitario: Decimal
    quantidade: int = 1


@dataclass
class ItemComanda(ComId):
    """Linha da comanda. `preco_unitario`, `nome_produto` e `nome_tamanho` são snapshots:
    renomear ou reprecificar o cardápio depois não altera o histórico."""

    produto_id: int
    tamanho_id: int
    nome_produto: str
    nome_tamanho: str
    preco_unitario: Decimal
    quantidade: int = 1
    observacao: str | None = None
    adicionais: list[AdicionalItem] = field(default_factory=list)
    id: int | None = None


@dataclass
class Comanda(ComId):
    cliente_nome: str
    aberta_em: datetime
    origem: OrigemComanda = OrigemComanda.BALCAO
    cliente_contato: str | None = None
    observacao: str | None = None
    status: StatusComanda = StatusComanda.ABERTA
    itens: list[ItemComanda] = field(default_factory=list)
    aberta_por_id: int | None = None  # None: aberta por um bot (Fase 5), que não é usuário
    fechada_por_id: int | None = None
    fechada_em: datetime | None = None
    total_fechado: Decimal | None = None  # snapshot gravado no fechamento
    id: int | None = None
