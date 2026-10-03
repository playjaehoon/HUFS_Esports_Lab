"""Add public gallery and notice boards, preserving the existing notice."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'board_post',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', sa.String(length=10), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('image_path', sa.String(length=200)),
        sa.Column('image_alt', sa.String(length=160)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("category IN ('notice','gallery')", name='board_post_category'),
        sa.CheckConstraint("(category = 'notice' AND image_path IS NULL) OR "
                           "(category = 'gallery' AND image_path IS NOT NULL)",
                           name='board_post_gallery_image'),
    )
    op.create_index('ix_board_post_category', 'board_post', ['category'])
    op.create_index('ix_board_post_created_at', 'board_post', ['created_at'])

    connection = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    notice = connection.execute(
        sa.text("SELECT value FROM setting WHERE key = 'notice'")
    ).scalar_one_or_none()
    if notice is None:
        notice = '이용 당일 학생증을 준비해 주세요.'
    posts = [
        ('gallery', '실습실 전경', 'Philips Evnia Esports Lab의 공간을 둘러보세요.',
         'images/home/slide-2.jpg', '모니터와 게이밍 의자가 놓인 실습실 전경'),
        ('gallery', '개관 현장', '실습실 개관 현장의 모습입니다.',
         'images/home/slide-1.jpg', '실습실 개관 행사에 함께한 사람들'),
        ('gallery', '실습실 이용 모습', '실습실에서 함께 플레이하는 모습입니다.',
         'images/home/slide-3.jpg', '실습실 좌석에서 게임을 플레이하는 이용자들'),
        ('gallery', '함께하는 시간', '실습실에서 활동하는 이용자들의 모습입니다.',
         'images/home/slide-4.jpg', '여러 좌석에서 PC를 이용하는 실습실 이용자들'),
    ]
    if notice and notice.strip():
        posts.append(('notice', '실습실 이용 안내', notice.strip(), None, None))
    for category, title, body, image_path, image_alt in posts:
        connection.execute(sa.text('''
            INSERT INTO board_post (category, title, body, image_path, image_alt, created_at, updated_at)
            VALUES (:category, :title, :body, :image_path, :image_alt, :created_at, :updated_at)
        '''), dict(category=category, title=title, body=body, image_path=image_path,
                   image_alt=image_alt, created_at=now, updated_at=now))


def downgrade():
    op.drop_index('ix_board_post_created_at', table_name='board_post')
    op.drop_index('ix_board_post_category', table_name='board_post')
    op.drop_table('board_post')
