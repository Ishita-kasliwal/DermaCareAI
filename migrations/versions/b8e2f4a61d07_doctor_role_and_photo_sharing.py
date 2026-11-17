"""doctor role (users.role + users.clinic_name) and appointments.share_photo

Revision ID: b8e2f4a61d07
Revises: a7d4e9b13c58
Create Date: 2026-11-17 10:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8e2f4a61d07'
down_revision = 'a7d4e9b13c58'
branch_labels = None
depends_on = None

OLD = sa.Enum('user', 'admin', name='user_role')
NEW = sa.Enum('user', 'admin', 'doctor', name='user_role')


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('role', existing_type=OLD, type_=NEW, existing_nullable=False)
        batch_op.add_column(sa.Column('clinic_name', sa.String(length=160), nullable=True))
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('share_photo', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_column('share_photo')
    op.execute("UPDATE users SET role = 'user' WHERE role = 'doctor'")
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('clinic_name')
        batch_op.alter_column('role', existing_type=NEW, type_=OLD, existing_nullable=False)
