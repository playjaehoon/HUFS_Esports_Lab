document.addEventListener('DOMContentLoaded', () => {
    const overview = document.querySelector('.admin-seat-overview');
    if (!overview) return;
    const buttons = [...overview.querySelectorAll('[data-seat-number]')];
    const panels = [...overview.querySelectorAll('.admin-seat-panel')];
    buttons.forEach(button => button.addEventListener('click', () => {
        overview.querySelector('[data-seat-detail-hint]').hidden = true;
        buttons.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
        panels.forEach(panel => { panel.hidden = panel.id !== button.getAttribute('aria-controls'); });
        const heading = overview.querySelector(`#adminSeatTitle${button.dataset.seatNumber}`);
        heading.focus({preventScroll: true});
        if (matchMedia('(max-width: 900px)').matches) heading.scrollIntoView({block: 'start'});
    }));
});
