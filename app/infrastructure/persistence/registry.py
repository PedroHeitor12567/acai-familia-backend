"""Importa todos os modelos para registrá-los no metadata (Alembic e testes usam `Base`).

Todo novo módulo com tabelas deve ser importado aqui.
"""

from app.infrastructure.persistence.auditoria import models as _auditoria
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.usuarios import models as _usuarios

__all__ = ["Base"]
_MODELOS = (_auditoria, _usuarios)
