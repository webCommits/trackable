document.addEventListener('DOMContentLoaded', function() {
    // ── Theme toggle ──
    const themeToggle = document.getElementById('theme-toggle');
    const htmlEl = document.documentElement;

    function applyTheme(theme) {
        if (theme === 'light') {
            htmlEl.setAttribute('data-theme', 'light');
        } else {
            htmlEl.removeAttribute('data-theme');
        }
        const metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (metaThemeColor) {
            metaThemeColor.content = theme === 'light' ? '#dce0e8' : '#292c3c';
        }
        if (themeToggle) {
            themeToggle.setAttribute('aria-label',
                theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode');
        }
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const isLight = htmlEl.getAttribute('data-theme') === 'light';
            const newTheme = isLight ? 'dark' : 'light';
            localStorage.setItem('theme', newTheme);
            applyTheme(newTheme);
        });
    }

    // ── Hamburger menu ──
    const hamburger = document.querySelector('.nav-hamburger');
    const nav       = document.querySelector('.site-nav');

    if (hamburger && nav) {
        function closeMenu() {
            nav.classList.remove('is-open');
            hamburger.classList.remove('is-open');
            hamburger.setAttribute('aria-expanded', 'false');
        }

        hamburger.addEventListener('click', function(e) {
            e.stopPropagation();
            const open = nav.classList.toggle('is-open');
            hamburger.classList.toggle('is-open', open);
            hamburger.setAttribute('aria-expanded', String(open));
        });

        hamburger.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                hamburger.click();
            }
        });

        nav.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', closeMenu);
        });

        document.addEventListener('click', function(e) {
            if (!nav.contains(e.target) && !hamburger.contains(e.target)) closeMenu();
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeMenu();
        });
    }

    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
    });

    // ── Set aria-current on active nav links ──
    document.querySelectorAll('.nav-link.active').forEach(function(link) {
        link.setAttribute('aria-current', 'page');
    });

    const defaultTodayInputs = document.querySelectorAll('input[type="date"][data-default-today]');
    defaultTodayInputs.forEach(function(input) {
        if (!input.value) {
            const today = new Date().toISOString().split('T')[0];
            input.value = today;
        }
    });

    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('.btn-form-submit, button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.dataset.originalText = submitBtn.textContent;
                submitBtn.textContent = 'Wird gespeichert…';
            }
        });

        // Re-enable submit buttons so Back button works
        const submitBtn = form.querySelector('.btn-form-submit, button[type="submit"]');
        if (submitBtn) {
            window.addEventListener('pageshow', function() {
                submitBtn.disabled = false;
                if (submitBtn.dataset.originalText) {
                    submitBtn.textContent = submitBtn.dataset.originalText;
                }
            });
        }
    });

    const tableRows = document.querySelectorAll('.table tbody tr');
    tableRows.forEach(row => {
        row.addEventListener('mouseenter', function() {
            this.style.transition = 'background-color 0.3s ease';
        });
    });
});