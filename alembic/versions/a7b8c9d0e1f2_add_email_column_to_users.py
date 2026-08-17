"""add email column to users

Revision ID: a7b8c9d0e1f2
Revises: 553363b9301d
Create Date: 2026-08-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = '553363b9301d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'email' not in columns:
        op.add_column('users', sa.Column('email', sa.String(150), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'email')
