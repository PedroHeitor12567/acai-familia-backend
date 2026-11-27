import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "caixa_sessoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("valor_abertura", sa.Numeric(12, 2), nullable=False),
        sa.Column("aberta_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("fechada_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column(
            "aberta_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("fechada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valor_esperado", sa.Numeric(12, 2), nullable=True),
        sa.Column("valor_contado", sa.Numeric(12, 2), nullable=True),
        sa.Column("diferenca", sa.Numeric(12, 2), nullable=True),
        sa.Column("observacao", sa.String(500), nullable=True),
        sa.CheckConstraint("status IN ('aberta','fechada')", name="ck_caixa_sessoes_status"),
        sa.CheckConstraint("valor_abertura >= 0", name="ck_caixa_sessoes_abertura"),
        sa.CheckConstraint(
            "status <> 'fechada' OR (fechada_em IS NOT NULL AND fechada_por_id IS NOT NULL "
            "AND valor_contado IS NOT NULL AND valor_esperado IS NOT NULL "
            "AND diferenca IS NOT NULL)",
            name="ck_caixa_sessoes_fechada_completa",
        ),
    )
    op.create_index(
        "ux_caixa_sessao_aberta",
        "caixa_sessoes",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'aberta'"),
    )
    op.create_index("ix_caixa_sessoes_aberta_em", "caixa_sessoes", [sa.text("aberta_em DESC")])

    op.create_table(
        "caixa_movimentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sessao_id", sa.Integer, sa.ForeignKey("caixa_sessoes.id"), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("motivo", sa.String(255), nullable=False),
        sa.Column("criado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tipo IN ('sangria','suprimento')", name="ck_caixa_movimentos_tipo"),
        sa.CheckConstraint("valor > 0", name="ck_caixa_movimentos_valor"),
    )
    op.create_index("ix_caixa_movimentos_sessao_id", "caixa_movimentos", ["sessao_id"])


def downgrade() -> None:
    op.drop_table("caixa_movimentos")
    op.drop_table("caixa_sessoes")
