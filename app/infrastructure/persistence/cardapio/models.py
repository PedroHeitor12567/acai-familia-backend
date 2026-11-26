from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, agora


class CategoriaModel(Base):
    __tablename__ = "categorias"
    __table_args__ = (UniqueConstraint("nome", name="uq_categorias_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class TamanhoModel(Base):
    __tablename__ = "tamanhos"
    __table_args__ = (UniqueConstraint("nome", name="uq_tamanhos_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ProdutoModel(Base):
    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("categoria_id", "nome", name="uq_produtos_categoria_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class ProdutoTamanhoModel(Base):
    __tablename__ = "produto_tamanhos"
    __table_args__ = (CheckConstraint("preco >= 0", name="ck_produto_tamanhos_preco"),)

    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), primary_key=True)
    tamanho_id: Mapped[int] = mapped_column(ForeignKey("tamanhos.id"), primary_key=True, index=True)
    preco: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class AdicionalModel(Base):
    __tablename__ = "adicionais"
    __table_args__ = (
        UniqueConstraint("nome", name="uq_adicionais_nome"),
        CheckConstraint("preco >= 0", name="ck_adicionais_preco"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    preco: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
