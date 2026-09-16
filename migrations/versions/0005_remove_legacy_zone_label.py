"""Remove the obsolete performance-zone line from the usage notice."""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    notice = connection.execute(
        sa.text("SELECT value FROM setting WHERE key = 'usage_notice'")
    ).scalar_one_or_none()
    if notice is None:
        return

    cleaned = notice.replace('\r\n', '\n')
    cleaned = '\n'.join(
        line for line in cleaned.split('\n')
        if line.strip() not in {'1–10번 고성능 PC', '- 1–10번 고성능 PC'}
    )
    cleaned = cleaned.replace('1–10번 고성능 PC · ', '')
    if cleaned != notice:
        connection.execute(
            sa.text("UPDATE setting SET value = :value WHERE key = 'usage_notice'"),
            {'value': cleaned},
        )


def downgrade():
    # Removed wording is intentionally not restored over a notice operators may edit later.
    pass
