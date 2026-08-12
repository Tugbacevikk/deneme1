"""add user durum column

Revision ID: 553363b9301d
Revises: 9b727c91d165
Create Date: 2026-08-12 10:10:19.880816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '553363b9301d'
down_revision: Union[str, Sequence[str], None] = '9b727c91d165'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('durum', sa.String(20), server_default='onaylandi'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'durum')
