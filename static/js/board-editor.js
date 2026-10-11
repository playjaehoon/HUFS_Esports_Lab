document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('#board-post-editor');
    if (!form) return;
    const cover = form.elements.image, extras = form.elements.attachments;
    const error = form.querySelector('[data-upload-error]');
    const previews = form.querySelector('[data-new-image-previews]');
    let urls = [], coverUrl;
    const extraWidth = form.elements.attachments_width;
    const checkFiles = () => {
        const added = [...extras.files], covers = cover ? [...cover.files] : [];
        const files = [...covers, ...added];
        const count = Number(form.dataset.existingImages) + added.length +
            (cover && !Number(form.dataset.existingImages) && covers.length ? 1 : 0);
        const message = files.length > 10 ? '대표 사진을 포함해 한 번에 10장까지 업로드할 수 있습니다.' :
            added.length && count > 20 ? '대표 사진을 포함해 총 20장까지 등록할 수 있습니다.' :
            files.some(file => file.size > 10 * 1024 * 1024) ? '각 사진은 10MB 이하로 선택해 주세요.' :
            files.some(file => !/\.(jpe?g|png|webp)$/i.test(file.name)) ? 'JPG·JPEG·PNG·WebP 파일을 선택해 주세요.' : '';
        error.textContent = message; error.hidden = !message;
        return !message;
    };
    document.querySelectorAll('[data-image-width]').forEach(control => {
        control.addEventListener('input', () => {
            control.parentElement.querySelector('output').value = `${control.value}%`;
            const targets = control.dataset.preview ? [document.getElementById(control.dataset.preview)] : previews.querySelectorAll('img');
            targets.forEach(image => { if (image) image.style.width = `${control.value}%`; });
        });
    });
    if (cover) cover.addEventListener('change', () => {
        if (coverUrl) URL.revokeObjectURL(coverUrl);
        const image = document.getElementById('cover-size-preview');
        if (cover.files[0] && checkFiles()) {
            coverUrl = URL.createObjectURL(cover.files[0]); image.src = coverUrl; image.hidden = false;
        }
    });
    extras.addEventListener('change', () => {
        urls.forEach(url => URL.revokeObjectURL(url)); urls = []; previews.replaceChildren();
        if (!checkFiles()) return;
        [...extras.files].forEach(file => {
            const tile = document.createElement('div'), image = document.createElement('img'), caption = document.createElement('p');
            const url = URL.createObjectURL(file); urls.push(url);
            image.src = url; image.alt = '추가 사진 크기 미리보기'; image.style.width = `${extraWidth.value}%`;
            caption.textContent = file.name; tile.append(image, caption); previews.append(tile);
        });
    });
    form.addEventListener('submit', event => {
        if (!checkFiles()) { event.preventDefault(); error.scrollIntoView({block: 'center'}); }
    });
});
