from io import BytesIO
from pathlib import Path

from PIL import Image

from conftest import csrf, login, post
from models import BoardPost, HomePopup, db


def photo_bytes():
    output = BytesIO()
    Image.effect_noise((512, 512), 80).convert('RGB').save(output, format='JPEG', quality=95)
    return output.getvalue()


def test_admin_can_link_notice_and_disable_home_popup(app):
    visitor = app.test_client()
    student = login(app)
    admin = login(app, admin=True)
    assert 'data-home-popup' not in visitor.get('/').get_data(as_text=True)
    assert visitor.get('/admin/popup').status_code == 302
    assert student.get('/admin/popup').status_code == 403
    assert post(student, '/admin/popup', {'enabled': '1', 'mode': 'custom', 'body': 'x'}).status_code == 403
    assert '메인 팝업 관리' in admin.get('/admin').get_data(as_text=True)

    assert admin.post('/admin/posts/new', data={
        'csrf_token': csrf(admin), 'category': 'notice', 'title': '긴급 운영 공지',
        'body': '개관 일정 안내', 'attachments_alt': '공지 안내 사진',
        'attachments': (BytesIO(photo_bytes()), 'notice.jpg')},
        content_type='multipart/form-data').status_code == 302
    with app.app_context():
        notice = db.session.scalar(db.select(BoardPost).where(BoardPost.title == '긴급 운영 공지'))
        notice_id = notice.id
    assert post(admin, '/admin/popup', {
        'enabled': '1', 'mode': 'notice', 'notice_id': str(notice_id)}).status_code == 302
    home = visitor.get('/').get_data(as_text=True)
    assert 'data-home-popup' in home and '긴급 운영 공지' in home
    assert '/board/image/' in home and '공지 안내 사진' in home
    assert '오늘 보지 않기' in home and 'data-popup-day="2026-09-14"' in home
    assert f'/notices/{notice_id}' in home
    assert 'data-home-popup' not in visitor.get('/notices').get_data(as_text=True)

    assert post(admin, f'/admin/posts/{notice_id}/edit', {
        'title': '변경된 공지', 'body': '일정이 변경되었습니다.'}).status_code == 302
    assert '변경된 공지' in visitor.get('/').get_data(as_text=True)
    assert post(admin, '/admin/popup', {'mode': 'notice', 'notice_id': str(notice_id)}).status_code == 302
    assert 'data-home-popup' not in visitor.get('/').get_data(as_text=True)
    assert post(admin, '/admin/popup', {'enabled': '1', 'mode': 'notice', 'notice_id': str(notice_id)}).status_code == 302
    assert post(admin, f'/admin/posts/{notice_id}/delete', {'confirm': '1'}).status_code == 302
    assert 'data-home-popup' not in visitor.get('/').get_data(as_text=True)


def test_custom_photo_text_validation_and_replacement(app):
    visitor = app.test_client()
    admin = login(app, admin=True)
    missing = post(admin, '/admin/popup', {'enabled': '1', 'mode': 'custom'})
    assert missing.status_code == 400
    assert '본문이나 사진을 입력해 주세요.' in missing.get_data(as_text=True)
    assert 'data-error-for="body"' in missing.get_data(as_text=True)
    assert '1080×1080px' in missing.get_data(as_text=True)
    assert post(admin, '/admin/popup', {
        'enabled': '1', 'mode': 'custom', 'body': '<script>alert(1)</script> 설명'}).status_code == 302
    text_home = visitor.get('/').get_data(as_text=True)
    assert '&lt;script&gt;' in text_home and '<script>alert(1)</script>' not in text_home

    photo = photo_bytes()
    assert len(photo) > 32 * 1024
    invalid = admin.post('/admin/popup', data={
        'csrf_token': csrf(admin), 'enabled': '1', 'mode': 'custom',
        'image': (BytesIO(photo), 'photo.jpg')}, content_type='multipart/form-data')
    assert invalid.status_code == 400
    saved = admin.post('/admin/popup', data={
        'csrf_token': csrf(admin), 'enabled': '1', 'mode': 'custom',
        'image_alt': '실습실 행사 사진', 'image': (BytesIO(photo), 'photo.jpg')},
        content_type='multipart/form-data')
    assert saved.status_code == 302
    with app.app_context():
        photo_popup = db.session.scalar(db.select(HomePopup).where(HomePopup.is_active.is_(True)))
        assert photo_popup is not None and photo_popup.image_path.startswith('uploads/')
        photo_popup_id = photo_popup.id
        assert db.session.scalar(db.select(db.func.count()).select_from(HomePopup)) == 2
    assert visitor.get('/popup/image').status_code == 200
    assert '실습실 행사 사진' in visitor.get('/').get_data(as_text=True)
    files = list(Path(app.config['BOARD_UPLOAD_DIR']).glob('*.jpg'))
    assert len(files) == 1
    assert post(admin, '/admin/popup', {
        'mode': 'custom', 'image_alt': '실습실 행사 사진'}).status_code == 302
    assert visitor.get('/popup/image').status_code == 404
    assert admin.get(f'/admin/popup/history/{photo_popup_id}/image').status_code == 200
    assert post(admin, '/admin/popup', {
        'enabled': '1', 'mode': 'custom', 'body': '새로운 텍스트',
        'remove_image': '1'}).status_code == 302
    assert visitor.get('/popup/image').status_code == 404
    assert files[0].exists()  # Historic popup images remain available for reactivation.
    assert '새로운 텍스트' in visitor.get('/').get_data(as_text=True)
    history = admin.get('/admin/popup').get_data(as_text=True)
    assert '이전 팝업' in history and '다시 게시' in history
    assert post(admin, f'/admin/popup/history/{photo_popup_id}/activate').status_code == 302
    assert visitor.get('/popup/image').status_code == 200
    assert '실습실 행사 사진' in visitor.get('/').get_data(as_text=True)
    assert post(admin, '/admin/popup/hide').status_code == 302
    assert 'data-home-popup' not in visitor.get('/').get_data(as_text=True)


def test_popup_rejects_missing_notice_and_fake_image(app):
    admin = login(app, admin=True)
    assert post(admin, '/admin/popup', {
        'enabled': '1', 'mode': 'notice', 'notice_id': '9999'}).status_code == 400
    response = admin.post('/admin/popup', data={
        'csrf_token': csrf(admin), 'enabled': '1', 'mode': 'custom',
        'image_alt': '가짜 사진', 'image': (BytesIO(b'<script>bad</script>'), 'bad.jpg')},
        content_type='multipart/form-data')
    assert response.status_code == 400
    assert '사진 파일을 읽을 수 없습니다' in response.get_data(as_text=True)
    upload_dir = Path(app.config['BOARD_UPLOAD_DIR'])
    assert not upload_dir.exists() or not list(upload_dir.glob('*.jpg'))
