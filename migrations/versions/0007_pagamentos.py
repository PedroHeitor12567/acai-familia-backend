import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pagamentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("comanda_id", sa.Integer, sa.ForeignKey("comandas.id"), nullable=False),
        sa.Column("sessao_id", sa.Integer, sa.ForeignKey("caixa_sessoes.id"), nullable=False),
        sa.Column("forma", sa.String(15), nullable=False),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False),
        sa.Column("valor_recebido", sa.Numeric(12, 2), nullable=True),
        sa.Column("criado_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "forma IN ('dinheiro','pix','cartao_debito','cartao_credito')",
            name="ck_pagamentos_forma",
        ),
        sa.CheckConstraint("valor > 0", name="ck_pagamentos_valor"),
        sa.CheckConstraint(
            "forma = 'dinheiro' OR valor_recebido IS NULL", name="ck_pagamentos_recebido_dinheiro"
        ),
        sa.CheckConstraint(
            "valor_recebido IS NULL OR valor_recebido >= valor", name="ck_pagamentos_recebido_valor"
        ),
    )
    op.create_index("ix_pagamentos_comanda_id", "pagamentos", ["comanda_id"])
    op.create_index(
        "ux_pagamentos_comanda_forma", "pagamentos", ["comanda_id", "forma"], unique=True
    )
    op.create_index("ix_pagamentos_sessao_forma", "pagamentos", ["sessao_id", "forma"])


def downgrade() -> None:
    op.drop_table("pagamentos")
