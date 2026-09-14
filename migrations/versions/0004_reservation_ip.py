"""Record the client address used to submit a reservation."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reservation') as batch:
        batch.add_column(sa.Column('booking_ip', sa.String(length=45), nullable=True))


def downgrade():
    with op.batch_alter_table('reservation') as batch:
        batch.drop_column('booking_ip')
