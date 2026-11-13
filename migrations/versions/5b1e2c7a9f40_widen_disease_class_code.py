"""widen disease_classes.code to 32 characters (e.g. 'contact_dermatitis')

Revision ID: 5b1e2c7a9f40
Revises: d074ff09e2cc
Create Date: 2026-11-11 01:05:00

"""
from alembic import op
import sqlalchemy as sa


revision = '5b1e2c7a9f40'
down_revision = 'd074ff09e2cc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('disease_classes', schema=None) as batch_op:
        batch_op.alter_column('code', existing_type=sa.String(length=16), type_=sa.String(length=32),
                              existing_nullable=False)


def downgrade():
    with op.batch_alter_table('disease_classes', schema=None) as batch_op:
        batch_op.alter_column('code', existing_type=sa.String(length=32), type_=sa.String(length=16),
                              existing_nullable=False)
