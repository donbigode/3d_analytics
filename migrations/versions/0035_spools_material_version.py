"""spools.material_version_id

Existe para o repositório 3d_analytics_medallion poder atribuir consumo de
filamento pela bobina de onde ele saiu, em vez de pelo único material do item
— que com multicor joga as gramas de todas as cores no mesmo material.
Ver gold/consumo.py lá, cuja própria docstring declara a limitação.

material_versions é SCD2 (effective_from/effective_to/is_current), com várias
linhas por (material_type, manufacturer, color). O vínculo certo é a versão
CORRENTE, e só quando ela é única: duas linhas is_current para o mesmo trio
não deveriam existir, mas o esquema não impede, e escolher arbitrariamente
seria vincular a bobina ao produto errado.

Nullable de propósito. Taxa de casamento baixa não é falha da migração — é
sinal de que os cadastros divergem.

Revision ID: 0035_spools_material_version
Revises: 0034_quote_item_filaments
Create Date: 2026-09-26 12:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_spools_material_version"
down_revision: Union[str, Sequence[str], None] = "0034_quote_item_filaments"
branch_labels = None
depends_on = None


# Correlated subquery: para cada spool, tenta achar exatamente 1 versão corrente
# com o mesmo (material_type, manufacturer, color). Se houver exatamente 1,
# atualiza. Se houver 0 ou 2+, deixa NULL.
# IS NOT DISTINCT FROM em vez de = porque color e manufacturer são nullable.
BACKFILL_SQL = """
UPDATE spools s
   SET material_version_id = (
     SELECT mv.id
       FROM material_versions mv
      WHERE mv.is_current
        AND mv.material_type = s.material_type
        AND mv.color IS NOT DISTINCT FROM s.color
        AND mv.manufacturer IS NOT DISTINCT FROM s.manufacturer
      LIMIT 1
   )
  WHERE s.material_version_id IS NULL
    AND 1 = (
     SELECT count(*)
       FROM material_versions mv
      WHERE mv.is_current
        AND mv.material_type = s.material_type
        AND mv.color IS NOT DISTINCT FROM s.color
        AND mv.manufacturer IS NOT DISTINCT FROM s.manufacturer
   )
"""


def upgrade() -> None:
    op.add_column(
        "spools",
        sa.Column("material_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_spools_material_version",
        "spools",
        "material_versions",
        ["material_version_id"],
        ["id"],
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_constraint("fk_spools_material_version", "spools", type_="foreignkey")
    op.drop_column("spools", "material_version_id")
