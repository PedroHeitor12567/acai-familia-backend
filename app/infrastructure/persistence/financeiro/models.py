from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, agora


class CategoriaFinanceiraModel(Base):
    __tablename__ = "categorias_financeiras"
    __table_args__ = (
        CheckConstraint("tipo IN ('receita','despesa')", name="ck_categorias_financeiras_tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(10))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


Index(
    "ux_categorias_financeiras_tipo_nome",
    CategoriaFinanceiraModel.tipo,
    func.lower(CategoriaFinanceiraModel.nome),
    unique=True,
)


class LancamentoModel(Base):
    __tablename__ = "lancamentos"
    __table_args__ = (
        CheckConstraint("tipo IN ('pagar','receber')", name="ck_lancamentos_tipo"),
        CheckConstraint("status IN ('pendente','pago','cancelado')", name="ck_lancamentos_status"),
        CheckConstraint("valor > 0", name="ck_lancamentos_valor"),
        CheckConstraint(
            "status <> 'pago' OR (data_pagamento IS NOT NULL AND forma_pagamento IS NOT NULL "
            "AND baixado_por_id IS NOT NULL)",
            name="ck_lancamentos_pago_completo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))
    descricao: Mapped[str] = mapped_column(String(160))
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    vencimento: Mapped[date] = mapped_column(Date)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias_financeiras.id"))
    contraparte: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(10))
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    forma_pagamento: Mapped[str | None] = mapped_column(String(15), nullable=True)
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    baixado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


Index("ix_lancamentos_status_vencimento", LancamentoModel.status, LancamentoModel.vencimento)
Index(
    "ix_lancamentos_status_data_pagamento", LancamentoModel.status, LancamentoModel.data_pagamento
)
Index("ix_lancamentos_categoria_id", LancamentoModel.categoria_id)
Index(
    "ix_lancamentos_pendentes",
    LancamentoModel.vencimento,
    postgresql_where=text("status = 'pendente'"),
    sqlite_where=text("status = 'pendente'"),
)
