from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.base import Base, agora


class ComandaModel(Base):
    __tablename__ = "comandas"
    __table_args__ = (
        CheckConstraint("status IN ('aberta','fechada','cancelada')", name="ck_comandas_status"),
        CheckConstraint("origem IN ('balcao','whatsapp')", name="ck_comandas_origem"),
        CheckConstraint(
            "status <> 'fechada' OR (fechada_em IS NOT NULL AND total IS NOT NULL)",
            name="ck_comandas_fechada_completa",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_nome: Mapped[str] = mapped_column(String(120))
    origem: Mapped[str] = mapped_column(String(10))
    cliente_contato: Mapped[str | None] = mapped_column(String(60), nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(10))
    aberta_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fechada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aberta_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    itens: Mapped[list["ItemComandaModel"]] = relationship(
        lazy="selectin",
        order_by="ItemComandaModel.id",
        cascade="all, delete-orphan",
    )


# Listagem por status (mais recentes primeiro), a tela "abertas" (índice parcial) e a busca por
# cliente sem diferenciar maiúsculas de minúsculas.
Index("ix_comandas_status_aberta_em", ComandaModel.status, ComandaModel.aberta_em.desc())
Index(
    "ix_comandas_abertas",
    ComandaModel.aberta_em,
    postgresql_where=text("status = 'aberta'"),
    sqlite_where=text("status = 'aberta'"),
)
Index("ix_comandas_cliente_nome_lower", func.lower(ComandaModel.cliente_nome))
# Dashboard: vendas, série, por hora e por forma filtram `status = 'fechada'` por `fechada_em`.
Index(
    "ix_comandas_fechadas_em",
    ComandaModel.fechada_em,
    postgresql_where=text("status = 'fechada'"),
    sqlite_where=text("status = 'fechada'"),
)


class ItemComandaModel(Base):
    __tablename__ = "itens_comanda"
    __table_args__ = (
        ForeignKeyConstraint(
            ["produto_id", "tamanho_id"],
            ["produto_tamanhos.produto_id", "produto_tamanhos.tamanho_id"],
        ),
        CheckConstraint("quantidade > 0", name="ck_itens_comanda_quantidade"),
        CheckConstraint("preco_unitario >= 0", name="ck_itens_comanda_preco"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comanda_id: Mapped[int] = mapped_column(
        ForeignKey("comandas.id", ondelete="CASCADE"), index=True
    )
    produto_id: Mapped[int] = mapped_column(Integer)
    tamanho_id: Mapped[int] = mapped_column(Integer)
    nome_produto: Mapped[str] = mapped_column(String(120))
    nome_tamanho: Mapped[str] = mapped_column(String(60))
    quantidade: Mapped[int] = mapped_column(Integer)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    observacao: Mapped[str | None] = mapped_column(String(500), nullable=True)

    adicionais: Mapped[list["ItemComandaAdicionalModel"]] = relationship(
        lazy="selectin",
        order_by="ItemComandaAdicionalModel.id",
        cascade="all, delete-orphan",
    )


# Ranking de mais vendidos e itens vendidos agrupam os itens da comanda por produto.
Index("ix_itens_comanda_comanda_produto", ItemComandaModel.comanda_id, ItemComandaModel.produto_id)


class ItemComandaAdicionalModel(Base):
    __tablename__ = "itens_comanda_adicional"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_itens_comanda_adicional_quantidade"),
        CheckConstraint("preco_unitario >= 0", name="ck_itens_comanda_adicional_preco"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("itens_comanda.id", ondelete="CASCADE"), index=True
    )
    adicional_id: Mapped[int] = mapped_column(ForeignKey("adicionais.id"))
    nome: Mapped[str] = mapped_column(String(80))
    quantidade: Mapped[int] = mapped_column(Integer)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2))
