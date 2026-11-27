import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorias_financeiras",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tipo IN ('receita','despesa')", name="ck_categorias_financeiras_tipo"),
    )
    op.create_index(
        "ux_categorias_financeiras_tipo_nome",
        "categorias_financeiras",
        ["tipo", sa.text("lower(nome)")],
        unique=True,
    )

    op.create_table(
        "lancamentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("descricao", sa.String(160), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("vencimento", sa.Date, nullable=False),
        sa.Column(
            "categoria_id", sa.Integer, sa.ForeignKey("categorias_financeiras.id"), nullable=False
        ),
        sa.Column("contraparte", sa.String(120), nullable=True),
        sa.Column("observacao", sa.String(500), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("data_pagamento", sa.Date, nullable=True),
        sa.Column("forma_pagamento", sa.String(15), nullable=True),
        sa.Column("criado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("baixado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("tipo IN ('pagar','receber')", name="ck_lancamentos_tipo"),
        sa.CheckConstraint(
            "status IN ('pendente','pago','cancelado')", name="ck_lancamentos_status"
        ),
        sa.CheckConstraint("valor > 0", name="ck_lancamentos_valor"),
        sa.CheckConstraint(
            "status <> 'pago' OR (data_pagamento IS NOT NULL AND forma_pagamento IS NOT NULL "
            "AND baixado_por_id IS NOT NULL)",
            name="ck_lancamentos_pago_completo",
        ),
    )
    op.create_index("ix_lancamentos_status_vencimento", "lancamentos", ["status", "vencimento"])
    op.create_index("ix_lancamentos_categoria_id", "lancamentos", ["categoria_id"])
    op.create_index(
        "ix_lancamentos_pendentes",
        "lancamentos",
        ["vencimento"],
        postgresql_where=sa.text("status = 'pendente'"),
    )


def downgrade() -> None:
    op.drop_table("lancamentos")
    op.drop_table("categorias_financeiras")
