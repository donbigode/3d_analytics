"""quote_item_filaments + material_consumptions.quote_item_filament_id

Um item passa a ter N filamentos. A tabela nova é autoritativa para custo;
quote_items.material_version_id continua existindo como derivado da linha 1,
para que o repositório 3d_analytics_medallion siga funcionando sem mudança
(expand/contract).

O backfill é PURAMENTE ESTRUTURAL: grams_unit fica NULL, que significa
"derive do gcode_meta como hoje". Gravar as gramas calculadas congelaria um
valor derivado e o histórico pararia de reprecificar quando a densidade do
material fosse ajustada.

BACKFILL_SQL é módulo-level de propósito: conftest.py roda as migrações antes
de qualquer dado de teste existir, então o teste do backfill importa esta
constante e a executa contra dados próprios. É o mesmo SQL que roda aqui.

Revision ID: 0034_quote_item_filaments
Revises: 0033_sales_quote_kind_backfill
Create Date: 2026-09-26 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_quote_item_filaments"
down_revision: Union[str, Sequence[str], None] = "0033_sales_quote_kind_backfill"
branch_labels = None
depends_on = None


# Idempotente pelo NOT EXISTS: rodar de novo não duplica.
# Itens sem material resolvido ficam sem linha — a invariante "todo item tem ao
# menos uma linha" vale a partir da resolução do material, que é o que
# _assert_materials_resolved já exige antes de produzir.
BACKFILL_SQL = """
INSERT INTO quote_item_filaments
       (id, quote_item_id, material_version_id, grams_unit, position)
SELECT gen_random_uuid(), qi.id, qi.material_version_id, NULL, 1
  FROM quote_items qi
 WHERE qi.material_version_id IS NOT NULL
   AND NOT EXISTS (
         SELECT 1 FROM quote_item_filaments f WHERE f.quote_item_id = qi.id
       )
"""


def upgrade() -> None:
    op.create_table(
        "quote_item_filaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quote_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quote_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("material_versions.id"),
            nullable=False,
        ),
        sa.Column("grams_unit", sa.Numeric(10, 2), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("quote_item_id", "position", name="uq_quote_item_filament_pos"),
    )
    op.create_index(
        "ix_quote_item_filaments_item", "quote_item_filaments", ["quote_item_id"]
    )

    op.add_column(
        "material_consumptions",
        sa.Column("quote_item_filament_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_material_consumptions_filament",
        "material_consumptions",
        "quote_item_filaments",
        ["quote_item_filament_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_constraint(
        "fk_material_consumptions_filament", "material_consumptions", type_="foreignkey"
    )
    op.drop_column("material_consumptions", "quote_item_filament_id")
    op.drop_index("ix_quote_item_filaments_item", table_name="quote_item_filaments")
    op.drop_table("quote_item_filaments")
