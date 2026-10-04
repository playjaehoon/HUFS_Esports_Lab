"""Public notice/gallery boards and staff-managed posts."""
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4

from flask import abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from PIL import Image, ImageOps, UnidentifiedImageError
from markupsafe import Markup
import nh3

from auth_helpers import admin_required
from booking import RuleError, event, write_transaction
from models import BoardAttachment, BoardPost, db, utcnow


IMAGE_LIMIT = 5 * 1024 * 1024
MAX_BATCH_IMAGES = 5
MAX_POST_IMAGES = 30
PIXEL_LIMIT = 20_000_000
Image.MAX_IMAGE_PIXELS = PIXEL_LIMIT
STATIC_IMAGES = {f'images/home/slide-{number}.jpg' for number in range(1, 5)}
UPLOAD_NAME = re.compile(r'uploads/[0-9a-f]{32}\.jpg\Z')
HTML_TAGS = {'p', 'br', 'strong', 'b', 'em', 'i', 'ul', 'ol', 'li', 'h2', 'h3', 'blockquote', 'a'}


def clean_html(value):
    return nh3.clean(value, tags=HTML_TAGS, attributes={'a': {'href', 'title'}},
                     url_schemes={'http', 'https', 'mailto'})


def display_html(value):
    return Markup(clean_html(value))


def posts_for(category):
    return db.select(BoardPost).where(BoardPost.category == category).order_by(
        BoardPost.created_at.desc(), BoardPost.id.desc())


def content(post_id, category):
    return db.first_or_404(db.select(BoardPost).where(BoardPost.id == post_id, BoardPost.category == category))


def stored_image(path):
    if not path or not UPLOAD_NAME.fullmatch(path):
        return None
    return upload_folder() / path.removeprefix('uploads/')


def upload_folder():
    return Path(current_app.config['BOARD_UPLOAD_DIR'] or Path(current_app.instance_path) / 'board_uploads')


def remove_old_image(path):
    old = stored_image(path)
    if old:
        try:
            old.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning('Could not remove superseded board image.')


def save_image(upload):
    raw = upload.read(IMAGE_LIMIT + 1)
    if len(raw) > IMAGE_LIMIT:
        raise RuleError('사진은 5MB 이하로 올려 주세요.')
    if not raw:
        raise RuleError('사진 파일을 선택해 주세요.')
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > PIXEL_LIMIT:
                raise RuleError('JPG·PNG·WebP 사진(2천만 화소 이하)만 올릴 수 있습니다.')
            source.load()
            oriented = ImageOps.exif_transpose(source)
            if oriented.mode in {'RGBA', 'LA'} or 'transparency' in oriented.info:
                rgba = oriented.convert('RGBA')
                image = Image.new('RGB', rgba.size, 'white')
                image.paste(rgba, mask=rgba.getchannel('A'))
            else:
                image = oriented.convert('RGB')
            image.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
            result = BytesIO()
            image.save(result, format='JPEG', quality=84, optimize=True, exif=b'')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise RuleError('사진 파일을 읽을 수 없습니다. JPG·PNG·WebP 파일을 확인해 주세요.') from exc
    folder = upload_folder()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = f'{uuid4().hex}.jpg'
    path = folder / name
    with path.open('xb') as output:
        output.write(result.getvalue())
    return f'uploads/{name}'


def fields(category):
    title = request.form.get('title', '').strip()
    body = request.form.get('body', '').strip()
    body_format = request.form.get('body_format', 'text')
    if body_format not in {'text', 'html'}:
        raise RuleError('본문 형식을 확인해 주세요.')
    image_alt = request.form.get('image_alt', '').strip() if category == 'gallery' else None
    if not 2 <= len(title) <= 120:
        raise RuleError('제목은 2~120자로 입력해 주세요.')
    if not 1 <= len(body) <= 10_000:
        raise RuleError('본문은 1~10,000자로 입력해 주세요.')
    if category == 'gallery' and not 2 <= len(image_alt) <= 160:
        raise RuleError('사진 설명은 2~160자로 입력해 주세요.')
    if body_format == 'html':
        body = clean_html(body)
        if not body.strip():
            raise RuleError('표시할 수 있는 본문 내용을 입력해 주세요.')
    return title, body, body_format, image_alt


def attachment_uploads(post):
    uploads = [file for file in request.files.getlist('attachments') if file.filename]
    if len(uploads) > MAX_BATCH_IMAGES:
        raise RuleError('사진은 한 번에 5장까지 추가할 수 있습니다. 저장 후 다시 추가해 주세요.')
    if len(uploads) + len(post.attachments) + (1 if post.category == 'gallery' else 0) > MAX_POST_IMAGES:
        raise RuleError('게시글에는 사진을 총 30장까지 올릴 수 있습니다.')
    alt = request.form.get('attachments_alt', '').strip()
    if uploads and not 2 <= len(alt) <= 160:
        raise RuleError('추가 사진 설명은 2~160자로 입력해 주세요.')
    return uploads, alt


def register_board_routes(app):
    app.jinja_env.filters['safe_board_html'] = display_html
    @app.route('/notices')
    def notice_board():
        page = max(1, request.args.get('page', default=1, type=int))
        posts = db.paginate(posts_for('notice'), page=page, per_page=10, error_out=False)
        return render_template('board_list.html', category='notice', posts=posts)

    @app.route('/gallery')
    def gallery_board():
        page = max(1, request.args.get('page', default=1, type=int))
        posts = db.paginate(posts_for('gallery'), page=page, per_page=9, error_out=False)
        return render_template('board_list.html', category='gallery', posts=posts)

    @app.route('/notices/<int:post_id>')
    def notice_post(post_id):
        return render_template('board_detail.html', category='notice', post=content(post_id, 'notice'))

    @app.route('/gallery/<int:post_id>')
    def gallery_post(post_id):
        return render_template('board_detail.html', category='gallery', post=content(post_id, 'gallery'))

    @app.route('/board/image/<int:post_id>')
    def board_image(post_id):
        post = content(post_id, 'gallery')
        if post.image_path in STATIC_IMAGES:
            return redirect(url_for('static', filename=post.image_path))
        path = stored_image(post.image_path)
        if path is None:
            abort(404)
        return send_from_directory(path.parent, path.name, mimetype='image/jpeg')

    @app.route('/board/image/<int:post_id>/<int:attachment_id>')
    def board_attachment_image(post_id, attachment_id):
        attachment = db.first_or_404(db.select(BoardAttachment).where(
            BoardAttachment.id == attachment_id, BoardAttachment.post_id == post_id))
        path = stored_image(attachment.image_path)
        if path is None:
            abort(404)
        return send_from_directory(path.parent, path.name, mimetype='image/jpeg')

    @app.route('/admin/posts')
    @admin_required
    def admin_posts():
        category = request.args.get('category', 'notice')
        if category not in {'notice', 'gallery'}:
            abort(404)
        page = max(1, request.args.get('page', default=1, type=int))
        posts = db.paginate(posts_for(category), page=page, per_page=20, error_out=False)
        return render_template('admin_posts.html', category=category, posts=posts)

    @app.route('/admin/posts/new', methods=['GET', 'POST'])
    @admin_required
    def admin_post_new():
        category = (request.form if request.method == 'POST' else request.args).get('category', 'notice')
        if category not in {'notice', 'gallery'}:
            abort(404)
        if request.method == 'POST':
            title, body, body_format, image_alt = fields(category)
            upload = request.files.get('image')
            if category == 'gallery' and (upload is None or not upload.filename):
                raise RuleError('갤러리 글에는 사진을 한 장 올려 주세요.')
            post = BoardPost(category=category, title=title, body=body, body_format=body_format,
                             image_path=None, image_alt=image_alt)
            uploads, alt = attachment_uploads(post)
            saved_paths = []
            try:
                image_path = save_image(upload) if category == 'gallery' else None
                if image_path:
                    saved_paths.append(image_path)
                paths = []
                for file in uploads:
                    path = save_image(file)
                    paths.append(path)
                    saved_paths.append(path)
                with write_transaction():
                    post.image_path = image_path
                    db.session.add(post)
                    db.session.flush()
                    for path in paths:
                        db.session.add(BoardAttachment(post_id=post.id, image_path=path, image_alt=alt))
                    event(f'admin:{current_user.id}', 'board_post_create', post.id, category)
                    post_id = post.id
            except Exception:
                for path in saved_paths:
                    remove_old_image(path)
                raise
            flash('게시글을 등록했습니다.')
            return redirect(url_for('gallery_post' if category == 'gallery' else 'notice_post', post_id=post_id))
        return render_template('admin_post_form.html', category=category, post=None)

    @app.route('/admin/posts/<int:post_id>/edit', methods=['GET', 'POST'])
    @admin_required
    def admin_post_edit(post_id):
        post = db.get_or_404(BoardPost, post_id)
        if request.method == 'POST':
            title, body, body_format, image_alt = fields(post.category)
            upload = request.files.get('image') if post.category == 'gallery' else None
            uploads, alt = attachment_uploads(post)
            saved_paths = []
            try:
                image_path = save_image(upload) if upload and upload.filename else None
                if image_path:
                    saved_paths.append(image_path)
                paths = []
                for file in uploads:
                    path = save_image(file)
                    paths.append(path)
                    saved_paths.append(path)
                with write_transaction():
                    post = db.get_or_404(BoardPost, post_id)
                    current_count = db.session.scalar(db.select(db.func.count()).select_from(BoardAttachment)
                                                      .where(BoardAttachment.post_id == post_id))
                    if current_count + len(paths) + (1 if post.category == 'gallery' else 0) > MAX_POST_IMAGES:
                        raise RuleError('게시글에는 사진을 총 30장까지 올릴 수 있습니다.')
                    old_path = post.image_path
                    post.title, post.body, post.body_format = title, body, body_format
                    post.image_alt, post.updated_at = image_alt, utcnow()
                    if image_path:
                        post.image_path = image_path
                    for path in paths:
                        db.session.add(BoardAttachment(post_id=post.id, image_path=path, image_alt=alt))
                    event(f'admin:{current_user.id}', 'board_post_edit', post.id, post.category)
            except Exception:
                for path in saved_paths:
                    remove_old_image(path)
                raise
            if image_path:
                remove_old_image(old_path)
            flash('게시글을 수정했습니다.')
            return redirect(url_for('admin_posts', category=post.category))
        return render_template('admin_post_form.html', category=post.category, post=post)

    @app.route('/admin/posts/<int:post_id>/images/<int:attachment_id>/delete', methods=['POST'])
    @admin_required
    def admin_attachment_delete(post_id, attachment_id):
        with write_transaction():
            attachment = db.first_or_404(db.select(BoardAttachment).where(
                BoardAttachment.id == attachment_id, BoardAttachment.post_id == post_id))
            path = attachment.image_path
            db.session.delete(attachment)
            event(f'admin:{current_user.id}', 'board_image_delete', post_id, str(attachment_id))
        remove_old_image(path)
        flash('사진을 삭제했습니다.')
        return redirect(url_for('admin_post_edit', post_id=post_id))

    @app.route('/admin/posts/<int:post_id>/delete', methods=['POST'])
    @admin_required
    def admin_post_delete(post_id):
        if request.form.get('confirm') != '1':
            raise RuleError('삭제 확인을 선택해 주세요.')
        with write_transaction():
            post = db.get_or_404(BoardPost, post_id)
            category, image_path = post.category, post.image_path
            attachment_paths = [item.image_path for item in post.attachments]
            db.session.delete(post)
            event(f'admin:{current_user.id}', 'board_post_delete', post_id, category)
        remove_old_image(image_path)
        for path in attachment_paths:
            remove_old_image(path)
        flash('게시글을 삭제했습니다.')
        return redirect(url_for('admin_posts', category=category))
