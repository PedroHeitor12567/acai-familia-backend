"""estoque: insumos e movimentações (histórico imutável)

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insumos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("unidade", sa.String(5), nullable=False),
        sa.Column("estoque_minimo", sa.Numeric(12, 3), nullable=False),
        sa.Column("estoque_atual", sa.Numeric(12, 3), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("nome", name="uq_insumos_nome"),
        sa.CheckConstraint("estoque_minimo >= 0", name="ck_insumos_estoque_minimo"),
    )
    op.create_table(
        "movimentacoes_estoque",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("insumo_id", sa.Integer, sa.ForeignKey("insumos.id"), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.Column("saldo_antes", sa.Numeric(12, 3), nullable=False),
        sa.Column("saldo_apos", sa.Numeric(12, 3), nullable=False),
        sa.Column("motivo", sa.String(255), nullable=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_movimentacoes_estoque_quantidade"),
    )
    op.create_index(
        "ix_movimentacoes_estoque_insumo_criado_em",
        "movimentacoes_estoque",
        ["insumo_id", "criado_em"],
    )
    op.create_index("ix_movimentacoes_estoque_usuario_id", "movimentacoes_estoque", ["usuario_id"])


def downgrade() -> None:
    op.drop_table("movimentacoes_estoque")
    op.drop_table("insumos")
