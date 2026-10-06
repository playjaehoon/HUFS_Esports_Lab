"""Staff-managed homepage popup with recoverable publishing history."""
from uuid import uuid4

from flask import abort, flash, redirect, render_template, request, send_from_directory, url_for

from auth_helpers import admin_required
from board_routes import posts_for, remove_old_image, save_image, stored_image
from booking import RuleError, event, write_transaction
from models import BoardPost, HomePopup, db, utcnow


def active_popup():
    return db.session.scalar(db.select(HomePopup).where(HomePopup.is_active.is_(True)))


def popup_entries():
    return db.session.scalars(db.select(HomePopup).order_by(HomePopup.id.desc())).all()


def visible_popup():
    config = active_popup()
    if config is None:
        return None
    if config.mode == 'notice':
        post = db.session.get(BoardPost, config.notice_id)
        if post is None or post.category != 'notice' or post.is_hidden:
            return None
        return {'config': config, 'notice': post,
                'version': f'{config.version}-{post.updated_at.isoformat()}'}
    if config.mode == 'custom' and (config.body or config.image_path):
        return {'config': config, 'notice': None, 'version': config.version}
    return None


def editor_data(source):
    return {'enabled': source.get('enabled', '0') == '1',
            'mode': source.get('mode', 'notice'), 'notice_id': source.get('notice_id', '').strip(),
            'title': source.get('title', '').strip(), 'body': source.get('body', '').strip(),
            'image_alt': source.get('image_alt', '').strip(),
            'remove_image': source.get('remove_image') == '1'}


def existing_data(entry):
    return {'enabled': bool(entry and entry.is_active), 'mode': entry.mode if entry else 'notice',
            'notice_id': str(entry.notice_id or '') if entry else '',
            'title': entry.title if entry else '', 'body': entry.body if entry else '',
            'image_alt': entry.image_alt if entry else '', 'remove_image': False}


def validate(draft, image_path, has_upload):
    errors = {}
    mode = draft['mode']
    if mode not in {'notice', 'custom'}:
        errors['mode'] = '팝업 형식을 선택해 주세요.'
    notice_id = None
    if draft['notice_id']:
        try:
            notice_id = int(draft['notice_id'])
        except ValueError:
            errors['notice_id'] = '공지사항을 다시 선택해 주세요.'
        else:
            post = db.session.get(BoardPost, notice_id) if notice_id > 0 else None
            if post is None or post.category != 'notice' or post.is_hidden:
                errors['notice_id'] = '공개 중인 공지사항을 선택해 주세요.'
    if draft['enabled'] and mode == 'notice' and notice_id is None and 'notice_id' not in errors:
        errors['notice_id'] = '팝업에 표시할 공지사항을 선택해 주세요.'
    if len(draft['title']) > 120:
        errors['title'] = '제목은 120자 이하로 입력해 주세요.'
    if len(draft['body']) > 3000:
        errors['body'] = '본문은 3,000자 이하로 입력해 주세요.'
    if len(draft['image_alt']) > 160:
        errors['image_alt'] = '사진 설명은 160자 이하로 입력해 주세요.'
    if draft['remove_image'] and has_upload:
        errors['image'] = '사진 교체와 삭제 중 하나만 선택해 주세요.'
    if draft['enabled'] and mode == 'custom' and not (draft['body'] or image_path or has_upload):
        errors['body'] = '본문이나 사진을 입력해 주세요.'
        errors['image'] = '본문을 쓰지 않는 경우 사진을 선택해 주세요.'
    if mode == 'custom' and (image_path or has_upload) and not draft['remove_image'] and not 2 <= len(draft['image_alt']) <= 160:
        errors['image_alt'] = '사진 설명을 2~160자로 입력해 주세요.'
    return errors, notice_id


def register_popup_routes(app):
    @app.route('/admin/popup', methods=['GET', 'POST'])
    @admin_required
    def admin_popup():
        entries = popup_entries()
        current = active_popup() or (entries[0] if entries else None)
        notices = db.session.scalars(posts_for('notice')).all()
        draft = editor_data(request.form) if request.method == 'POST' else existing_data(current)
        errors = {}
        if request.method == 'POST':
            upload = request.files.get('image')
            has_upload = bool(upload and upload.filename)
            old_image = current.image_path if current else None
            image_path = None if draft['remove_image'] else old_image
            errors, notice_id = validate(draft, image_path, has_upload)
            if not errors and has_upload:
                try:
                    image_path = save_image(upload)
                except RuleError as exc:
                    errors['image'] = str(exc)
            if errors:
                return render_template('admin_popup.html', draft=draft, current=current,
                                       entries=entries, notices=notices, errors=errors), 400
            try:
                with write_transaction():
                    for entry in db.session.scalars(db.select(HomePopup).where(HomePopup.is_active.is_(True))):
                        entry.is_active = False
                    has_content = ((draft['mode'] == 'notice' and notice_id is not None) or
                                   (draft['mode'] == 'custom' and (draft['body'] or image_path)))
                    if has_content:
                        db.session.flush()
                        db.session.add(HomePopup(mode=draft['mode'], notice_id=notice_id,
                                                 title=draft['title'], body=draft['body'],
                                                 image_path=image_path, image_alt=draft['image_alt'],
                                                 is_active=draft['enabled'], version=uuid4().hex))
                    event('admin', 'home_popup_update', 'home_popup',
                          f"{draft['mode']}; active={draft['enabled']}")
            except Exception:
                if has_upload and image_path:
                    remove_old_image(image_path)
                raise
            flash('팝업을 저장했습니다. 이전 팝업은 아래 목록에서 확인할 수 있습니다.')
            return redirect(url_for('admin_popup'))
        return render_template('admin_popup.html', draft=draft, current=current,
                               entries=entries, notices=notices, errors=errors)

    @app.post('/admin/popup/history/<int:entry_id>/activate')
    @admin_required
    def admin_popup_activate(entry_id):
        entry = db.get_or_404(HomePopup, entry_id)
        if entry.mode == 'notice':
            notice = db.session.get(BoardPost, entry.notice_id)
            if notice is None or notice.category != 'notice' or notice.is_hidden:
                flash('이 팝업의 공지사항이 삭제되거나 숨겨졌습니다. 먼저 공지사항을 공개해 주세요.')
                return redirect(url_for('admin_popup'))
        elif not (entry.body or (entry.image_path and stored_image(entry.image_path) and
                                 stored_image(entry.image_path).is_file())):
            flash('이 팝업은 본문이나 사진이 없어 다시 게시할 수 없습니다.')
            return redirect(url_for('admin_popup'))
        with write_transaction():
            for active in db.session.scalars(db.select(HomePopup).where(HomePopup.is_active.is_(True))):
                active.is_active = False
            db.session.flush()
            entry = db.session.get(HomePopup, entry_id)
            entry.is_active = True
            entry.version = uuid4().hex
            entry.updated_at = utcnow()
            event('admin', 'home_popup_activate', entry_id)
        flash('이전 팝업을 다시 게시했습니다.')
        return redirect(url_for('admin_popup'))

    @app.post('/admin/popup/hide')
    @admin_required
    def admin_popup_hide():
        with write_transaction():
            entry = active_popup()
            if entry:
                entry.is_active = False
                event('admin', 'home_popup_hide', entry.id)
        flash('메인 팝업을 숨겼습니다.')
        return redirect(url_for('admin_popup'))

    @app.route('/popup/image')
    def popup_image():
        entry = active_popup()
        if entry is None or entry.mode != 'custom':
            abort(404)
        path = stored_image(entry.image_path)
        if path is None or not path.is_file():
            abort(404)
        return send_from_directory(path.parent, path.name, mimetype='image/jpeg')

    @app.route('/admin/popup/history/<int:entry_id>/image')
    @admin_required
    def admin_popup_history_image(entry_id):
        entry = db.get_or_404(HomePopup, entry_id)
        path = stored_image(entry.image_path)
        if path is None or not path.is_file():
            abort(404)
        return send_from_directory(path.parent, path.name, mimetype='image/jpeg')
