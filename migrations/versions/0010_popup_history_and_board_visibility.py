"""Keep popup history and allow staff to hide board posts without deleting them."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('board_post') as batch:
        batch.add_column(sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='0'))

    op.create_table(
        'home_popup',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mode', sa.String(length=10), nullable=False),
        sa.Column('notice_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('image_path', sa.String(length=200), nullable=True),
        sa.Column('image_alt', sa.String(length=160), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('version', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("mode IN ('notice','custom')", name='home_popup_mode'),
    )
    op.create_index('ix_home_popup_created_at', 'home_popup', ['created_at'])
    op.create_index('uq_home_popup_one_active', 'home_popup', ['is_active'], unique=True,
                    sqlite_where=sa.text('is_active = 1'))

    # The first popup implementation stored one item in Setting. Bring that
    # item into the list without changing its content or visibility.
    bind = op.get_bind()
    raw = bind.execute(sa.text("SELECT value FROM setting WHERE key='home_popup'")).scalar()
    try:
        previous = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        previous = None
    if isinstance(previous, dict):
        mode = previous.get('mode')
        notice_id = previous.get('notice_id')
        body = previous.get('body') or ''
        image_path = previous.get('image_path')
        if mode == 'notice' and isinstance(notice_id, int) and notice_id > 0 or (
                mode == 'custom' and (body or image_path)):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            bind.execute(sa.text('''
                INSERT INTO home_popup
                (mode, notice_id, title, body, image_path, image_alt, is_active, version, created_at, updated_at)
                VALUES (:mode, :notice_id, :title, :body, :image_path, :image_alt, :is_active,
                        :version, :created_at, :updated_at)
            '''), {'mode': mode, 'notice_id': notice_id, 'title': previous.get('title') or '',
                   'body': body, 'image_path': image_path, 'image_alt': previous.get('image_alt') or '',
                   'is_active': bool(previous.get('enabled')), 'version': previous.get('version') or uuid4().hex,
                   'created_at': now, 'updated_at': now})


def downgrade():
    bind = op.get_bind()
    row = bind.execute(sa.text('''SELECT mode, notice_id, title, body, image_path, image_alt, is_active, version
                                  FROM home_popup ORDER BY is_active DESC, id DESC LIMIT 1''')).mappings().first()
    if row:
        config = {'enabled': bool(row['is_active']), 'mode': row['mode'], 'notice_id': row['notice_id'],
                  'title': row['title'], 'body': row['body'], 'image_path': row['image_path'],
                  'image_alt': row['image_alt'], 'version': row['version']}
        value = json.dumps(config, ensure_ascii=False)
        if bind.execute(sa.text("SELECT 1 FROM setting WHERE key='home_popup'")).scalar():
            bind.execute(sa.text("UPDATE setting SET value=:value WHERE key='home_popup'"), {'value': value})
        else:
            bind.execute(sa.text("INSERT INTO setting (key, value) VALUES ('home_popup', :value)"), {'value': value})
    op.drop_index('uq_home_popup_one_active', table_name='home_popup')
    op.drop_index('ix_home_popup_created_at', table_name='home_popup')
    op.drop_table('home_popup')
    with op.batch_alter_table('board_post') as batch:
        batch.drop_column('is_hidden')
