"""add users.google_sub for "Continue with Google"

Revision ID: 9c3f1a7d2b60
Revises: 5b1e2c7a9f40
Create Date: 2026-11-15 23:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = '9c3f1a7d2b60'
down_revision = '5b1e2c7a9f40'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_sub', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('uq_users_google_sub', ['google_sub'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_google_sub', type_='unique')
        batch_op.drop_column('google_sub')
