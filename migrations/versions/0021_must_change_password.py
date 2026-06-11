"""users.must_change_password

Revision ID: 0021_must_change_password
Revises: 0020_material_waste
Create Date: 2026-06-10 09:00:00.000000

Flag pra forçar troca de senha no primeiro login. Usuários seedados em
prod entram com `must_change_password=True` e o frontend bloqueia
navegação até trocar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_must_change_password"
down_revision: Union[str, Sequence[str], None] = "0020_material_waste"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
