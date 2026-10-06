(() => {
    const menu = document.querySelector('.site-menu');
    if (menu) {
        document.addEventListener('click', event => {
            if (menu.open && !menu.contains(event.target)) menu.open = false;
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && menu.open) {
                menu.open = false;
                menu.querySelector('summary').focus();
            }
        });
        menu.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { menu.open = false; }));
    }

    const department = document.querySelector('[data-department-select]');
    const otherField = document.querySelector('[data-department-other]');
    if (department && otherField) {
        const otherInput = otherField.querySelector('input');
        const syncDepartment = () => {
            const isOther = ['목록에 없는 학과', '서울캠퍼스 학과'].includes(department.value);
            otherField.hidden = !isOther;
            otherInput.disabled = !isOther;
            otherInput.required = isOther;
            otherInput.maxLength = 100 - department.value.length - 2;
        };
        department.addEventListener('change', syncDepartment);
        syncDepartment();
    }

    const logoRail = document.querySelector('[data-logo-rail]');
    if (logoRail) {
        const originalLogos = logoRail.querySelector('.logo-rail-set');
        const repeatedLogos = originalLogos.cloneNode(true);
        repeatedLogos.setAttribute('aria-hidden', 'true');
        repeatedLogos.setAttribute('inert', '');
        repeatedLogos.querySelectorAll('img').forEach(img => { img.alt = ''; });
        repeatedLogos.querySelectorAll('a').forEach(link => { link.tabIndex = -1; });
        logoRail.appendChild(repeatedLogos);
        logoRail.classList.add('is-scrolling');
    }

    const popupEditor = document.querySelector('.popup-editor');
    if (popupEditor) {
        const showError = (name, message) => {
            const target = popupEditor.querySelector(`[data-error-for="${name}"]`);
            if (target) target.textContent = message;
            const field = popupEditor.elements.namedItem(name);
            if (field?.setAttribute) field.setAttribute('aria-invalid', message ? 'true' : 'false');
        };
        const syncMode = () => {
            const mode = popupEditor.querySelector('input[name="mode"]:checked')?.value;
            popupEditor.querySelectorAll('[data-popup-mode]').forEach(section => {
                section.hidden = section.dataset.popupMode !== mode;
            });
        };
        popupEditor.querySelectorAll('input[name="mode"]').forEach(input => input.addEventListener('change', syncMode));
        popupEditor.addEventListener('input', event => {
            if (event.target.name) showError(event.target.name, '');
        });
        popupEditor.addEventListener('change', event => {
            if (event.target.name) showError(event.target.name, '');
        });
        popupEditor.addEventListener('submit', event => {
            popupEditor.querySelectorAll('[data-error-for]').forEach(item => showError(item.dataset.errorFor, ''));
            const mode = popupEditor.querySelector('input[name="mode"]:checked')?.value;
            const enabled = popupEditor.elements.namedItem('enabled').value === '1';
            const file = popupEditor.elements.namedItem('image').files[0];
            const remove = popupEditor.elements.namedItem('remove_image')?.checked || false;
            const hasImage = popupEditor.dataset.hasImage === '1' && !remove;
            let first;
            const fail = (name, message) => {
                showError(name, message);
                if (!first) first = popupEditor.elements.namedItem(name);
            };
            if (enabled && mode === 'notice' && !popupEditor.elements.namedItem('notice_id').value)
                fail('notice_id', '팝업에 표시할 공지사항을 선택해 주세요.');
            if (mode === 'custom') {
                const body = popupEditor.elements.namedItem('body').value.trim();
                const alt = popupEditor.elements.namedItem('image_alt').value.trim();
                if (enabled && !body && !hasImage && !file) {
                    fail('body', '본문이나 사진을 입력해 주세요.');
                    fail('image', '본문을 쓰지 않는 경우 사진을 선택해 주세요.');
                }
                if (file && remove) fail('image', '사진 교체와 삭제 중 하나만 선택해 주세요.');
                if (file && (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024))
                    fail('image', 'JPG·PNG·WebP 사진을 5MB 이하로 선택해 주세요.');
                if ((file || hasImage) && (alt.length < 2 || alt.length > 160))
                    fail('image_alt', '사진 설명을 2~160자로 입력해 주세요.');
            }
            if (first) { event.preventDefault(); first.focus(); first.scrollIntoView({block: 'center', behavior: 'smooth'}); }
        });
        syncMode();
    }

    const homePopup = document.querySelector('[data-home-popup]');
    if (homePopup) {
        const key = `home-popup:${homePopup.dataset.popupVersion}:${homePopup.dataset.popupDay}`;
        let hiddenToday = false;
        try { hiddenToday = window.localStorage.getItem(key) === '1'; } catch (_) { /* Private browsing can block storage. */ }
        if (!hiddenToday) {
            if (typeof homePopup.showModal === 'function') homePopup.showModal();
            else homePopup.setAttribute('open', '');
        }
        homePopup.querySelectorAll('[data-popup-close]').forEach(button => button.addEventListener('click', () => {
            if (typeof homePopup.close === 'function') homePopup.close();
            else homePopup.removeAttribute('open');
        }));
        homePopup.querySelector('[data-popup-today]').addEventListener('click', () => {
            try { window.localStorage.setItem(key, '1'); } catch (_) { /* Current page can still close. */ }
            if (typeof homePopup.close === 'function') homePopup.close();
            else homePopup.removeAttribute('open');
        });
    }

    const viewport = document.querySelector('[data-carousel]');
    if (!viewport) return;
    const track = viewport.querySelector('.hero-track');
    const slides = Array.from(track.children);
    const number = document.querySelector('[data-slide-number]');
    const prev = document.querySelector('[data-carousel-prev]');
    const next = document.querySelector('[data-carousel-next]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let position = 1;
    let moving = false;
    let timer;

    const firstCopy = slides[0].cloneNode(true);
    const lastCopy = slides[slides.length - 1].cloneNode(true);
    firstCopy.setAttribute('aria-hidden', 'true');
    lastCopy.setAttribute('aria-hidden', 'true');
    firstCopy.querySelector('img').alt = '';
    lastCopy.querySelector('img').alt = '';
    track.prepend(lastCopy);
    track.appendChild(firstCopy);

    function render(animate = true) {
        track.style.transition = animate ? '' : 'none';
        track.style.transform = `translateX(-${position * 100}%)`;
        number.textContent = String(((position - 1 + slides.length) % slides.length) + 1).padStart(2, '0');
    }

    function move(direction) {
        if (reducedMotion.matches) {
            position = ((position - 1 + direction + slides.length) % slides.length) + 1;
            render(false);
            return;
        }
        if (moving) return;
        moving = true;
        position += direction;
        render();
    }

    function stop() {
        window.clearInterval(timer);
        timer = undefined;
    }

    function start() {
        stop();
        if (!reducedMotion.matches && !document.hidden) timer = window.setInterval(() => move(1), 3000);
    }

    track.addEventListener('transitionend', event => {
        if (event.propertyName === 'transform') {
            if (position === 0 || position === slides.length + 1) {
                position = position === 0 ? slides.length : 1;
                render(false);
            }
            moving = false;
        }
    });
    prev.addEventListener('click', () => { move(-1); start(); });
    next.addEventListener('click', () => { move(1); start(); });
    if (window.matchMedia('(hover: hover)').matches) {
        viewport.closest('.home-hero').addEventListener('mouseenter', stop);
        viewport.closest('.home-hero').addEventListener('mouseleave', start);
    }
    viewport.closest('.home-hero').addEventListener('focusin', stop);
    viewport.closest('.home-hero').addEventListener('focusout', event => {
        if (!event.currentTarget.contains(event.relatedTarget)) start();
    });
    document.addEventListener('visibilitychange', start);
    reducedMotion.addEventListener('change', start);
    render(false);
    track.offsetWidth;
    start();
})();
