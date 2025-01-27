"""Initial schema with all columns

Revision ID: 7f8c41d2e123
Revises: 
Create Date: 2024-01-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '7f8c41d2e123'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('subscription_tier', sa.String(), server_default='free'),
        sa.Column('pages_used_this_month', sa.Integer(), server_default='0'),
        sa.Column('subscription_start', sa.DateTime(), nullable=True),
        sa.Column('subscription_end', sa.DateTime(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('uq_verification_token', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('uq_verification_token')
    )

    op.create_table('transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('transactions')
    op.drop_table('users')