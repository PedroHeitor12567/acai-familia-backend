"""Importa todos os modelos para registrá-los no metadata (Alembic e testes usam `Base`).

Todo novo módulo com tabelas deve ser importado aqui.
"""

from app.infrastructure.persistence.auditoria import models as _auditoria
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.caixa import models as _caixa
from app.infrastructure.persistence.cardapio import models as _cardapio
from app.infrastructure.persistence.comandas import models as _comandas
from app.infrastructure.persistence.estoque import models as _estoque
from app.infrastructure.persistence.financeiro import models as _financeiro
from app.infrastructure.persistence.usuarios import models as _usuarios

__all__ = ["Base"]
_MODELOS = (_auditoria, _caixa, _cardapio, _comandas, _estoque, _financeiro, _usuarios)
