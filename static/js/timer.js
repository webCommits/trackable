(function() {
    'use strict';

    const timers = new Map();
    const POLL_INTERVAL = 5000;

    function formatTime(totalSeconds) {
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        return [hours, minutes, seconds]
            .map(v => String(v).padStart(2, '0'))
            .join(':');
    }

    function updateTimerDisplay(profileId) {
        const timerData = timers.get(profileId);
        
        const displayEl = document.querySelector(`.timer-display[data-profile-id="${profileId}"]`);
        const controlsEl = document.querySelector(`.timer-controls[data-profile-id="${profileId}"]`);
        if (!displayEl || !controlsEl) return;

        if (!timerData || !timerData.hasTimer) {
            displayEl.textContent = '';
            displayEl.removeAttribute('data-running');
            updateButtonStates(controlsEl, { hasTimer: false });
            return;
        }

        const now = Date.now() / 1000;
        let elapsedSeconds;

        if (timerData.isPaused) {
            elapsedSeconds = timerData.elapsedSeconds;
        } else {
            elapsedSeconds = timerData.elapsedSeconds + (now - timerData.lastUpdate);
        }

        displayEl.textContent = formatTime(Math.floor(Math.max(0, elapsedSeconds)));
        displayEl.setAttribute('data-running', !timerData.isPaused);

        updateButtonStates(controlsEl, timerData);
    }

    function updateButtonStates(controlsEl, timerData) {
        const startBtn = controlsEl.querySelector('[data-action="start"]');
        const pauseBtn = controlsEl.querySelector('[data-action="pause"]');
        const resumeBtn = controlsEl.querySelector('[data-action="resume"]');
        const stopBtn = controlsEl.querySelector('[data-action="stop"]');

        if (!startBtn || !pauseBtn || !resumeBtn || !stopBtn) return;

        startBtn.style.display = 'none';
        pauseBtn.style.display = 'none';
        resumeBtn.style.display = 'none';
        stopBtn.style.display = 'none';

        if (!timerData.hasTimer) {
            startBtn.style.display = 'inline-block';
        } else if (timerData.isPaused) {
            resumeBtn.style.display = 'inline-block';
            stopBtn.style.display = 'inline-block';
        } else {
            pauseBtn.style.display = 'inline-block';
            stopBtn.style.display = 'inline-block';
        }
    }

    async function fetchTimerStatus(profileId) {
        try {
            const response = await fetch(`/timer/${profileId}/status/`);
            const data = await response.json();

            if (data.has_timer) {
                const now = Date.now() / 1000;
                timers.set(profileId, {
                    hasTimer: true,
                    isPaused: data.is_paused,
                    elapsedSeconds: data.elapsed_seconds,
                    lastUpdate: now
                });
                updateTimerDisplay(profileId);
            } else {
                timers.set(profileId, {
                    hasTimer: false,
                    isPaused: false,
                    elapsedSeconds: 0,
                    lastUpdate: 0
                });
            }
        } catch (error) {
            console.error('Error fetching timer status:', error);
        }
    }

    async function handleTimerAction(profileId, action) {
        const timerData = timers.get(profileId);
        if (!timerData) return;

        try {
            const response = await fetch(`/timer/${profileId}/${action}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken()
                }
            });

            const data = await response.json();

            if (!response.ok) {
                console.error('Timer action failed:', data.error);
                return;
            }

            const now = Date.now() / 1000;

            switch (action) {
                case 'start':
                    timers.set(profileId, {
                        hasTimer: true,
                        isPaused: false,
                        elapsedSeconds: 0,
                        lastUpdate: now
                    });
                    break;
                case 'pause':
                    if (timerData && !timerData.isPaused) {
                        timerData.isPaused = true;
                        timerData.elapsedSeconds = Math.floor(
                            timerData.elapsedSeconds + (now - timerData.lastUpdate)
                        );
                        timers.set(profileId, timerData);
                    }
                    break;
                case 'resume':
                    if (timerData && timerData.isPaused) {
                        timerData.isPaused = false;
                        timerData.lastUpdate = now;
                        timers.set(profileId, timerData);
                    }
                    break;
                case 'stop':
                    timers.delete(profileId);
                    if (data.message) {
                        showNotification(data.message, 'success');
                    }
                    updateTimerDisplay(profileId);
                    setTimeout(() => fetchTimerStatus(profileId), 500);
                    return;
            }

            updateTimerDisplay(profileId);

            if (!timerData.isPaused && action !== 'pause') {
                fetchTimerStatus(profileId);
            }
        } catch (error) {
            console.error('Timer action error:', error);
        }
    }

    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               document.cookie.split('; ')
                   .find(row => row.startsWith('csrftoken='))
                   ?.split('=')[1];
    }

    function showNotification(message, type) {
        const existing = document.querySelector('.timer-notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.className = `timer-notification timer-notification-${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'success' ? '#40a02b' : '#f43f5e'};
            color: white;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    function initTimerControls() {
        document.querySelectorAll('.timer-controls').forEach(controlsEl => {
            const profileId = controlsEl.getAttribute('data-profile-id');
            if (!profileId) return;

            controlsEl.addEventListener('click', function(e) {
                const button = e.target.closest('[data-action]');
                if (!button) return;

                const action = button.getAttribute('data-action');
                handleTimerAction(profileId, action);
            });
        });
    }

    function initAllTimers() {
        document.querySelectorAll('.timer-controls').forEach(controlsEl => {
            const profileId = controlsEl.getAttribute('data-profile-id');
            if (profileId) {
                fetchTimerStatus(profileId);
            }
        });
    }

    setInterval(() => {
        timers.forEach((timerData, profileId) => {
            if (timerData.hasTimer && !timerData.isPaused && timerData.lastUpdate > 0) {
                updateTimerDisplay(profileId);
            }
        });
    }, 1000);

    setInterval(() => {
        timers.forEach((_, profileId) => {
            fetchTimerStatus(profileId);
        });
    }, POLL_INTERVAL);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initTimerControls();
            initAllTimers();
        });
    } else {
        initTimerControls();
        initAllTimers();
    }
})();
