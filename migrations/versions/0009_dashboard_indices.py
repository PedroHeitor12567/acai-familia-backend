"""Dashboard: somente índices (nenhuma tabela nova).

Já existem e foram conferidos, então não são recriados: `ix_comandas_status_aberta_em` (cobre o
contador de comandas abertas, `status` é a coluna líder), `ix_pagamentos_comanda_id` (join por
comanda) e `ux_pagamentos_comanda_forma`. `insumos` é uma tabela pequena (dezenas de linhas), então
o estoque crítico não ganha índice próprio.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_comandas_fechadas_em",
        "comandas",
        ["fechada_em"],
        postgresql_where=sa.text("status = 'fechada'"),
    )
    op.create_index(
        "ix_itens_comanda_comanda_produto", "itens_comanda", ["comanda_id", "produto_id"]
    )
    op.create_index(
        "ix_lancamentos_status_data_pagamento", "lancamentos", ["status", "data_pagamento"]
    )


def downgrade() -> None:
    op.drop_index("ix_lancamentos_status_data_pagamento", table_name="lancamentos")
    op.drop_index("ix_itens_comanda_comanda_produto", table_name="itens_comanda")
    op.drop_index("ix_comandas_fechadas_em", table_name="comandas")
