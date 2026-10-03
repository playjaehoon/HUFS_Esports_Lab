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
