from io import BytesIO
from pathlib import Path

from PIL import Image

from conftest import csrf, login, post
from models import BoardPost, db


def test_public_boards_show_recent_posts_and_admin_can_manage_notices(app):
    visitor = app.test_client()
    admin = login(app, admin=True)
    dashboard = admin.get('/admin').get_data(as_text=True)
    assert '이용 시 유의사항 수정' in dashboard
    assert '/admin/posts?category=notice' in dashboard
    assert '/admin/posts?category=gallery' in dashboard
    student = login(app)
    for number in range(4):
        response = post(admin, '/admin/posts/new', {
            'category': 'notice', 'title': f'운영 공지 {number}', 'body': f'안내 본문 {number}'})
        assert response.status_code == 302
    home = visitor.get('/').get_data(as_text=True)
    assert '운영 공지 3' in home and '운영 공지 1' in home
    assert '운영 공지 0' not in home
    assert '이용 방법' in home
    assert all(label in home for label in ('회원가입', '좌석 예약', '학생증 확인', '실습실 이용'))
    assert home.index('id="notices"') < home.index('id="gallery"')
    assert '예약하고, 방문하세요.' not in home
    assert 'VISIT THE LAB' not in home
    assert 'HUFS GLOBAL CAMPUS · ROOM 335' not in home
    board = visitor.get('/notices').get_data(as_text=True)
    assert board.index('운영 공지 3') < board.index('운영 공지 0')
    with app.app_context():
        newest = db.session.scalar(db.select(BoardPost).order_by(BoardPost.id.desc()))
        identifier = newest.id
    assert '안내 본문 3' in visitor.get(f'/notices/{identifier}').get_data(as_text=True)
    assert student.post('/admin/posts/new', data={'csrf_token': csrf(student)}).status_code == 403
    assert post(admin, f'/admin/posts/{identifier}/edit', {
        'title': '변경된 공지', 'body': '수정된 안내'}).status_code == 302
    assert '변경된 공지' in visitor.get(f'/notices/{identifier}').get_data(as_text=True)
    assert post(admin, f'/admin/posts/{identifier}/delete', {'confirm': '1'}).status_code == 302
    assert visitor.get(f'/notices/{identifier}').status_code == 404
    assert 'board_post_delete' in admin.get('/admin/audit').get_data(as_text=True)


def jpeg_with_metadata():
    image = Image.effect_noise((512, 512), 80).convert('RGB')
    exif = Image.Exif()
    exif[315] = 'PRIVATE-EXIF-MARKER'
    output = BytesIO()
    image.save(output, format='JPEG', quality=95, exif=exif)
    return output.getvalue()


def test_gallery_upload_is_converted_and_private_metadata_removed(app):
    admin = login(app, admin=True)
    visitor = app.test_client()
    original = jpeg_with_metadata()
    assert len(original) > 32 * 1024  # Exceeds the ordinary form limit.
    response = admin.post('/admin/posts/new', data={
        'csrf_token': csrf(admin), 'category': 'gallery', 'title': '새 사진',
        'body': '사진 설명입니다.', 'image_alt': '실습실 좌석 사진',
        'image': (BytesIO(original), 'photo.jpg'),
    }, content_type='multipart/form-data')
    assert response.status_code == 302
    with app.app_context():
        entry = db.session.scalar(db.select(BoardPost).where(BoardPost.title == '새 사진'))
        identifier, filename = entry.id, entry.image_path
        image_file = Path(app.config['BOARD_UPLOAD_DIR']) / filename.removeprefix('uploads/')
        assert image_file.is_file()
        with Image.open(image_file) as saved:
            assert saved.format == 'JPEG'
            assert saved.getexif().get(315) is None
    assert visitor.get(f'/board/image/{identifier}').status_code == 200
    assert '새 사진' in visitor.get('/gallery').get_data(as_text=True)
    assert visitor.get(f'/gallery/{identifier}').status_code == 200
    assert post(admin, f'/admin/posts/{identifier}/delete', {'confirm': '1'}).status_code == 302
    assert not image_file.exists()
    assert visitor.get(f'/board/image/{identifier}').status_code == 404


def test_gallery_rejects_non_image(app):
    admin = login(app, admin=True)
    response = admin.post('/admin/posts/new', data={
        'csrf_token': csrf(admin), 'category': 'gallery', 'title': '잘못된 파일',
        'body': '내용', 'image_alt': '사진 설명',
        'image': (BytesIO(b'<script>alert(1)</script>'), 'fake.jpg'),
    }, content_type='multipart/form-data')
    assert response.status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(BoardPost)) == 0
    upload_dir = Path(app.config['BOARD_UPLOAD_DIR'])
    assert not upload_dir.exists() or not list(upload_dir.iterdir())
