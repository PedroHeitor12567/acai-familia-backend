from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, agora


class SessaoCaixaModel(Base):
    __tablename__ = "caixa_sessoes"
    __table_args__ = (
        CheckConstraint("status IN ('aberta','fechada')", name="ck_caixa_sessoes_status"),
        CheckConstraint("valor_abertura >= 0", name="ck_caixa_sessoes_abertura"),
        CheckConstraint(
            "status <> 'fechada' OR (fechada_em IS NOT NULL AND fechada_por_id IS NOT NULL "
            "AND valor_contado IS NOT NULL AND valor_esperado IS NOT NULL "
            "AND diferenca IS NOT NULL)",
            name="ck_caixa_sessoes_fechada_completa",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    valor_abertura: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    aberta_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fechada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aberta_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valor_esperado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    valor_contado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    diferenca: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)


Index(
    "ux_caixa_sessao_aberta",
    SessaoCaixaModel.status,
    unique=True,
    postgresql_where=text("status = 'aberta'"),
    sqlite_where=text("status = 'aberta'"),
)
Index("ix_caixa_sessoes_aberta_em", SessaoCaixaModel.aberta_em.desc())


class MovimentoCaixaModel(Base):
    __tablename__ = "caixa_movimentos"
    __table_args__ = (
        CheckConstraint("tipo IN ('sangria','suprimento')", name="ck_caixa_movimentos_tipo"),
        CheckConstraint("valor > 0", name="ck_caixa_movimentos_valor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("caixa_sessoes.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    motivo: Mapped[str] = mapped_column(String(255))
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class PagamentoModel(Base):
    __tablename__ = "pagamentos"
    __table_args__ = (
        CheckConstraint(
            "forma IN ('dinheiro','pix','cartao_debito','cartao_credito')",
            name="ck_pagamentos_forma",
        ),
        CheckConstraint("valor > 0", name="ck_pagamentos_valor"),
        CheckConstraint(
            "forma = 'dinheiro' OR valor_recebido IS NULL", name="ck_pagamentos_recebido_dinheiro"
        ),
        CheckConstraint(
            "valor_recebido IS NULL OR valor_recebido >= valor", name="ck_pagamentos_recebido_valor"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), index=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("caixa_sessoes.id"))
    forma: Mapped[str] = mapped_column(String(15))
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    valor_recebido: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    criado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


Index("ux_pagamentos_comanda_forma", PagamentoModel.comanda_id, PagamentoModel.forma, unique=True)
Index("ix_pagamentos_sessao_forma", PagamentoModel.sessao_id, PagamentoModel.forma)
