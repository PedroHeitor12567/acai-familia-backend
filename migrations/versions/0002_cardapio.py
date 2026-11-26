"""cardápio: categorias, tamanhos, produtos, preços por tamanho e adicionais

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _criado_em() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        _criado_em(),
        sa.UniqueConstraint("nome", name="uq_categorias_nome"),
    )
    op.create_table(
        "tamanhos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(60), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        _criado_em(),
        sa.UniqueConstraint("nome", name="uq_tamanhos_nome"),
    )
    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("categoria_id", sa.Integer, sa.ForeignKey("categorias.id"), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        _criado_em(),
        sa.UniqueConstraint("categoria_id", "nome", name="uq_produtos_categoria_nome"),
    )
    op.create_index("ix_produtos_categoria_id", "produtos", ["categoria_id"])
    op.create_table(
        "produto_tamanhos",
        sa.Column("produto_id", sa.Integer, sa.ForeignKey("produtos.id"), primary_key=True),
        sa.Column("tamanho_id", sa.Integer, sa.ForeignKey("tamanhos.id"), primary_key=True),
        sa.Column("preco", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("preco >= 0", name="ck_produto_tamanhos_preco"),
    )
    op.create_index("ix_produto_tamanhos_tamanho_id", "produto_tamanhos", ["tamanho_id"])
    op.create_table(
        "adicionais",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("preco", sa.Numeric(12, 2), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        _criado_em(),
        sa.UniqueConstraint("nome", name="uq_adicionais_nome"),
        sa.CheckConstraint("preco >= 0", name="ck_adicionais_preco"),
    )


def downgrade() -> None:
    op.drop_table("adicionais")
    op.drop_table("produto_tamanhos")
    op.drop_table("produtos")
    op.drop_table("tamanhos")
    op.drop_table("categorias")
