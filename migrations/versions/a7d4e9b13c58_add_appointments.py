"""add appointments (appointment requests from the "Find a dermatologist" clinic cards)

Revision ID: a7d4e9b13c58
Revises: 9c3f1a7d2b60
Create Date: 2026-11-17 00:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7d4e9b13c58'
down_revision = '9c3f1a7d2b60'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('public_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('prediction_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
        sa.Column('clinic_name', sa.String(length=160), nullable=False),
        sa.Column('clinic_address', sa.String(length=255), nullable=True),
        sa.Column('clinic_phone', sa.String(length=40), nullable=True),
        sa.Column('clinic_lat', sa.Float(), nullable=True),
        sa.Column('clinic_lon', sa.Float(), nullable=True),
        sa.Column('patient_name', sa.String(length=80), nullable=False),
        sa.Column('patient_phone', sa.String(length=10), nullable=False),
        sa.Column('preferred_date', sa.Date(), nullable=False),
        sa.Column('time_slot', sa.String(length=10), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('predicted_condition', sa.String(length=120), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id'),
    )
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_appointments_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointments_created_at'), ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_appointments_created_at'))
        batch_op.drop_index(batch_op.f('ix_appointments_user_id'))
    op.drop_table('appointments')
