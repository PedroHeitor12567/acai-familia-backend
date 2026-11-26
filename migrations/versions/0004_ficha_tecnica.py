"""ficha técnica: receitas por produto/tamanho e por adicional

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "itens_ficha_tecnica",
        sa.Column("produto_id", sa.Integer, primary_key=True),
        sa.Column("tamanho_id", sa.Integer, primary_key=True),
        sa.Column("insumo_id", sa.Integer, sa.ForeignKey("insumos.id"), primary_key=True),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.ForeignKeyConstraint(
            ["produto_id", "tamanho_id"],
            ["produto_tamanhos.produto_id", "produto_tamanhos.tamanho_id"],
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_itens_ficha_tecnica_quantidade"),
    )
    op.create_index("ix_itens_ficha_tecnica_insumo_id", "itens_ficha_tecnica", ["insumo_id"])
    op.create_table(
        "itens_ficha_adicional",
        sa.Column("adicional_id", sa.Integer, sa.ForeignKey("adicionais.id"), primary_key=True),
        sa.Column("insumo_id", sa.Integer, sa.ForeignKey("insumos.id"), primary_key=True),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("quantidade > 0", name="ck_itens_ficha_adicional_quantidade"),
    )
    op.create_index("ix_itens_ficha_adicional_insumo_id", "itens_ficha_adicional", ["insumo_id"])


def downgrade() -> None:
    op.drop_table("itens_ficha_adicional")
    op.drop_table("itens_ficha_tecnica")
