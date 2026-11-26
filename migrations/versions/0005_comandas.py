"""comandas: comandas, itens e adicionais dos itens (preços e nomes congelados)

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comandas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cliente_nome", sa.String(120), nullable=False),
        sa.Column("origem", sa.String(10), nullable=False),
        sa.Column("cliente_contato", sa.String(60), nullable=True),
        sa.Column("observacao", sa.String(500), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("aberta_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("fechada_por_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column(
            "aberta_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("fechada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.CheckConstraint("status IN ('aberta','fechada','cancelada')", name="ck_comandas_status"),
        sa.CheckConstraint("origem IN ('balcao','whatsapp')", name="ck_comandas_origem"),
        sa.CheckConstraint(
            "status <> 'fechada' OR (fechada_em IS NOT NULL AND total IS NOT NULL)",
            name="ck_comandas_fechada_completa",
        ),
    )
    op.create_index(
        "ix_comandas_status_aberta_em", "comandas", ["status", sa.text("aberta_em DESC")]
    )
    op.create_index(
        "ix_comandas_abertas",
        "comandas",
        ["aberta_em"],
        postgresql_where=sa.text("status = 'aberta'"),
    )
    op.create_index("ix_comandas_cliente_nome_lower", "comandas", [sa.text("lower(cliente_nome)")])

    op.create_table(
        "itens_comanda",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "comanda_id",
            sa.Integer,
            sa.ForeignKey("comandas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("produto_id", sa.Integer, nullable=False),
        sa.Column("tamanho_id", sa.Integer, nullable=False),
        sa.Column("nome_produto", sa.String(120), nullable=False),
        sa.Column("nome_tamanho", sa.String(60), nullable=False),
        sa.Column("quantidade", sa.Integer, nullable=False),
        sa.Column("preco_unitario", sa.Numeric(12, 2), nullable=False),
        sa.Column("observacao", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["produto_id", "tamanho_id"],
            ["produto_tamanhos.produto_id", "produto_tamanhos.tamanho_id"],
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_itens_comanda_quantidade"),
        sa.CheckConstraint("preco_unitario >= 0", name="ck_itens_comanda_preco"),
    )
    op.create_index("ix_itens_comanda_comanda_id", "itens_comanda", ["comanda_id"])

    op.create_table(
        "itens_comanda_adicional",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer,
            sa.ForeignKey("itens_comanda.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adicional_id", sa.Integer, sa.ForeignKey("adicionais.id"), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("quantidade", sa.Integer, nullable=False),
        sa.Column("preco_unitario", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantidade > 0", name="ck_itens_comanda_adicional_quantidade"),
        sa.CheckConstraint("preco_unitario >= 0", name="ck_itens_comanda_adicional_preco"),
    )
    op.create_index("ix_itens_comanda_adicional_item_id", "itens_comanda_adicional", ["item_id"])


def downgrade() -> None:
    op.drop_table("itens_comanda_adicional")
    op.drop_table("itens_comanda")
    op.drop_table("comandas")  # leva junto os índices da tabela
