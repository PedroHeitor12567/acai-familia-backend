from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, agora


class InsumoModel(Base):
    __tablename__ = "insumos"
    __table_args__ = (
        UniqueConstraint("nome", name="uq_insumos_nome"),
        CheckConstraint("estoque_minimo >= 0", name="ck_insumos_estoque_minimo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    unidade: Mapped[str] = mapped_column(String(5))
    estoque_minimo: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    estoque_atual: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class MovimentacaoEstoqueModel(Base):
    __tablename__ = "movimentacoes_estoque"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_movimentacoes_estoque_quantidade"),
        Index("ix_movimentacoes_estoque_insumo_criado_em", "insumo_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id"))
    tipo: Mapped[str] = mapped_column(String(10))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    saldo_antes: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    saldo_apos: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    motivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True, index=True
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ItemFichaTecnicaModel(Base):
    """Receita de (produto, tamanho): um insumo no máximo uma vez (chave primária)."""

    __tablename__ = "itens_ficha_tecnica"
    __table_args__ = (
        ForeignKeyConstraint(
            ["produto_id", "tamanho_id"],
            ["produto_tamanhos.produto_id", "produto_tamanhos.tamanho_id"],
        ),
        CheckConstraint("quantidade > 0", name="ck_itens_ficha_tecnica_quantidade"),
    )

    produto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tamanho_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id"), primary_key=True, index=True)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class ItemFichaAdicionalModel(Base):
    """Receita de um adicional (consumo por porção)."""

    __tablename__ = "itens_ficha_adicional"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_itens_ficha_adicional_quantidade"),
    )

    adicional_id: Mapped[int] = mapped_column(ForeignKey("adicionais.id"), primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id"), primary_key=True, index=True)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3))
