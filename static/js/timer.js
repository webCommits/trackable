(function() {
    'use strict';

    /* ═══════════════════════════════════════════════════════════════
     * Offline-Resilient Timer
     *
     * Design:
     *   - Jede Timer-Aktion (start/stop/pause/resume) wird sofort
     *     optimistisch im lokalen State abgebildet
     *   - Gleichzeitig wandert sie in eine localStorage-Queue
     *   - Ein Hintergrundprozess verarbeitet die Queue FIFO pro
     *     Profil und sendet die Client-Timestamps mit
     *   - Bei Erfolg fliegt der Eintrag raus, bei Fehler bleibt
     *     er drin (exponentielles Backoff + Retry)
     *   - Bei Seitenladung: Queue + Server-State reconcilieren
     * ═══════════════════════════════════════════════════════════════ */

    // ── Globals ──────────────────────────────────────────────────
    const timers = new Map();           // lokaler Timer-State (wie bisher)
    const POLL_INTERVAL = 5000;         // Server-Poll-Intervall (ms)
    const QUEUE_RETRY_BASE = 1000;      // Basis für exponentielles Backoff (ms)
    const QUEUE_RETRY_MAX = 30000;      // Max Backoff (30s)
    const QUEUE_PERIODIC = 10000;       // Queue-Processing alle 10s

    const QUEUE_KEY = 'timer_queue';
    const PENDING_BADGE_CLASS = 'timer-pending-badge';

    // ── Queue-Management ─────────────────────────────────────────

    function getQueue() {
        try {
            return JSON.parse(localStorage.getItem(QUEUE_KEY)) || [];
        } catch {
            return [];
        }
    }

    function saveQueue(queue) {
        try {
            localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
        } catch (e) {
            console.warn('Could not save timer queue to localStorage:', e);
        }
    }

    function generateId() {
        return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    }

    function enqueue(profileId, action, payload) {
        const queue = getQueue();
        queue.push({
            id: generateId(),
            profileId: profileId,
            action: action,
            clientTimestamp: new Date().toISOString(),
            payload: payload || {},
            retryCount: 0,
            createdAt: Date.now(),
            lastAttempt: null,
        });
        saveQueue(queue);
        updatePendingBadge();
        processQueue(); // sofort versuchen
    }

    function removeFromQueue(id) {
        const queue = getQueue().filter(item => item.id !== id);
        saveQueue(queue);
        updatePendingBadge();
    }

    function getPendingForProfile(profileId) {
        return getQueue().filter(item => item.profileId == profileId);
    }

    function getQueueLength() {
        return getQueue().length;
    }

    function markAttempt(id) {
        const queue = getQueue();
        const item = queue.find(i => i.id === id);
        if (item) {
            item.retryCount++;
            item.lastAttempt = Date.now();
            saveQueue(queue);
        }
    }

    // ── Queue-Verarbeitung ───────────────────────────────────────

    async function processQueue() {
        const queue = getQueue();
        if (queue.length === 0) return;

        // Gruppiere nach Profil, verarbeite FIFO pro Profil
        const byProfile = {};
        for (const item of queue) {
            if (!byProfile[item.profileId]) byProfile[item.profileId] = [];
            byProfile[item.profileId].push(item);
        }

        for (const [profileId, items] of Object.entries(byProfile)) {
            for (const item of items) {
                // Abgelaufenes Backoff? Nicht vor Ablauf retryen
                if (item.lastAttempt) {
                    const wait = Math.min(
                        QUEUE_RETRY_BASE * Math.pow(2, item.retryCount),
                        QUEUE_RETRY_MAX
                    );
                    if (Date.now() - item.lastAttempt < wait) {
                        continue; // noch warten
                    }
                }

                const success = await processQueueItem(item);
                if (success) {
                    removeFromQueue(item.id);
                } else {
                    markAttempt(item.id);
                }
            }
        }

        updatePendingBadge();
    }

    async function processQueueItem(item) {
        try {
            // Vorab Server-Status holen, um obsolete Aktionen zu erkennen
            const statusResp = await fetch(`/timer/${item.profileId}/status/`);
            const status = await statusResp.json();

            // Reconcile: Ist die Aktion aus Sicht des Servers noch sinnvoll?
            if (!isActionValid(item.action, status)) {
                // obsolete Aktion → rauswerfen
                return true;
            }

            const resp = await fetch(`/timer/${item.profileId}/${item.action}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(Object.assign(
                    { client_timestamp: item.clientTimestamp },
                    item.payload || {}
                )),
            });

            const data = await resp.json();

            if (resp.ok) {
                // Bei Stop: Notification wie bisher
                if (item.action === 'stop' && data.message) {
                    showNotification(data.message, 'success');
                }
                // Lokalen State nachführen (Server sagt uns den aktuellen Zustand)
                reconcileLocalState(item.profileId, item.action, data);
                return true;
            }

            // Fehler vom Server (400, 404, etc.)
            // "Timer already running" bei Start → jemand anderes hat gestartet
            if (item.action === 'start' && resp.status === 400) {
                return true; // obsolete
            }
            // "No active timer found" bei Stop/Pause → Timer existiert nicht mehr
            if (['stop', 'pause'].includes(item.action) && resp.status === 404) {
                return true; // wurde schon verarbeitet
            }
            // "Timer is already paused" / "not paused" → Zustandskonflikt
            if (resp.status === 400) {
                return true; // Server sagt was anderes → Queue-Item obsolet
            }

            // Bei Validierungsfehler (400) bei Stop → Modal mit Fehler wieder öffnen,
            // State neu vom Server laden (war optimistisch bereits gelöscht)
            if (resp.status === 400 && item.action === 'stop') {
                try {
                    showStopError(item.profileId, data.error || 'Validierungsfehler');
                } catch (e) { /* Modal existiert evtl. nicht mehr */ }
                fetchTimerStatus(item.profileId);
                return true; // aus Queue entfernen, User muss erneut bestätigen
            }

            // anderer Fehler → wiederholen
            return false;

        } catch (err) {
            // Netzwerkfehler → wiederholen
            return false;
        }
    }

    function isActionValid(action, status) {
        switch (action) {
            case 'start':
                return !status.has_timer;
            case 'stop':
                return status.has_timer;
            case 'pause':
                return status.has_timer && !status.is_paused;
            case 'resume':
                return status.has_timer && status.is_paused;
            default:
                return true;
        }
    }

    // ── State-Reconciliation ─────────────────────────────────────

    function reconcileLocalState(profileId, action, data) {
        const now = Date.now() / 1000;

        switch (action) {
            case 'start':
                // Timer läuft jetzt auf dem Server mit bekanntem start_time
                const serverStartMs = new Date(data.start_time).getTime();
                const elapsed = (now * 1000 - serverStartMs) / 1000;
                timers.set(profileId, {
                    hasTimer: true,
                    isPaused: false,
                    elapsedSeconds: Math.max(0, elapsed),
                    lastUpdate: now,
                });
                break;

            case 'stop':
                timers.delete(profileId);
                break;

            case 'pause':
                {
                    const td = timers.get(profileId);
                    if (td && !td.isPaused) {
                        td.isPaused = true;
                        td.elapsedSeconds = Math.floor(
                            td.elapsedSeconds + (now - td.lastUpdate)
                        );
                        timers.set(profileId, td);
                    }
                }
                break;

            case 'resume':
                {
                    const td = timers.get(profileId);
                    if (td && td.isPaused) {
                        td.isPaused = false;
                        td.lastUpdate = now;
                        timers.set(profileId, td);
                    }
                }
                break;
        }

        updateTimerDisplay(profileId);
    }

    // ── Optimistischer lokaler State (sofort nach User-Klick) ───

    function applyOptimisticState(profileId, action) {
        const now = Date.now() / 1000;
        const td = timers.get(profileId);

        switch (action) {
            case 'start':
                timers.set(profileId, {
                    hasTimer: true,
                    isPaused: false,
                    elapsedSeconds: 0,
                    lastUpdate: now,
                });
                break;

            case 'pause':
                if (td && !td.isPaused) {
                    td.isPaused = true;
                    td.elapsedSeconds = Math.floor(
                        td.elapsedSeconds + (now - td.lastUpdate)
                    );
                    timers.set(profileId, td);
                }
                break;

            case 'resume':
                if (td && td.isPaused) {
                    td.isPaused = false;
                    td.lastUpdate = now;
                    timers.set(profileId, td);
                }
                break;

            case 'stop':
                timers.delete(profileId);
                break;
        }

        updateTimerDisplay(profileId);
    }

    // ── Timer-Display & Button-States (unverändert) ──────────────

    function formatTime(totalSeconds) {
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
    }

    function updateTimerDisplay(profileId) {
        const td = timers.get(profileId);
        const displayEl = document.querySelector(
            `.timer-display[data-profile-id="${profileId}"]`
        );
        const controlsEl = document.querySelector(
            `.timer-controls[data-profile-id="${profileId}"]`
        );
        if (!displayEl || !controlsEl) return;

        if (!td || !td.hasTimer) {
            displayEl.textContent = '';
            displayEl.removeAttribute('data-running');
            updateButtonStates(controlsEl, { hasTimer: false });
            return;
        }

        const now = Date.now() / 1000;
        const elapsed = td.isPaused
            ? td.elapsedSeconds
            : td.elapsedSeconds + (now - td.lastUpdate);

        displayEl.textContent = formatTime(Math.floor(Math.max(0, elapsed)));
        displayEl.setAttribute('data-running', !td.isPaused);
        updateButtonStates(controlsEl, td);
    }

    function updateButtonStates(controlsEl, state) {
        const startBtn = controlsEl.querySelector('[data-action="start"]');
        const pauseBtn = controlsEl.querySelector('[data-action="pause"]');
        const resumeBtn = controlsEl.querySelector('[data-action="resume"]');
        const stopBtn = controlsEl.querySelector('[data-action="stop"]');
        if (!startBtn || !pauseBtn || !resumeBtn || !stopBtn) return;

        startBtn.style.display = 'none';
        pauseBtn.style.display = 'none';
        resumeBtn.style.display = 'none';
        stopBtn.style.display = 'none';

        if (!state.hasTimer) {
            startBtn.style.display = 'inline-block';
        } else if (state.isPaused) {
            resumeBtn.style.display = 'inline-block';
            stopBtn.style.display = 'inline-block';
        } else {
            pauseBtn.style.display = 'inline-block';
            stopBtn.style.display = 'inline-block';
        }
    }

    // ── API-Calls ────────────────────────────────────────────────

    async function handleTimerAction(profileId, action) {
        applyOptimisticState(profileId, action);
        enqueue(profileId, action);
    }

    async function fetchTimerStatus(profileId) {
        try {
            const resp = await fetch(`/timer/${profileId}/status/`);
            const data = await resp.json();

            if (data.has_timer) {
                const now = Date.now() / 1000;
                timers.set(profileId, {
                    hasTimer: true,
                    isPaused: data.is_paused,
                    elapsedSeconds: data.elapsed_seconds,
                    lastUpdate: now,
                });
                // pausedSeconds ins Modal-Dataset schreiben für populateStopModal
                const modal = document.getElementById('stop-modal-' + profileId);
                if (modal) {
                    modal.dataset.pausedSeconds = String(data.total_paused_seconds || 0);
                }
            } else {
                timers.set(profileId, {
                    hasTimer: false,
                    isPaused: false,
                    elapsedSeconds: 0,
                    lastUpdate: 0,
                });
            }
            updateTimerDisplay(profileId);
        } catch (_) {
            // Stumm bei Netzwerkfehler
        }
    }

    // ── CSRF ─────────────────────────────────────────────────────

    function getCsrfToken() {
        return (
            document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
            document.cookie
                .split('; ')
                .find(row => row.startsWith('csrftoken='))
                ?.split('=')[1]
        );
    }

    // ── Notification ─────────────────────────────────────────────

    function showNotification(message, type) {
        const existing = document.querySelector('.timer-notification');
        if (existing) existing.remove();

        const el = document.createElement('div');
        el.className = 'timer-notification';
        el.textContent = message;
        el.style.cssText = [
            'position: fixed',
            'bottom: 20px',
            'right: 20px',
            'padding: 12px 20px',
            'background: ' + (type === 'success' ? '#40a02b' : '#f43f5e'),
            'color: white',
            'border-radius: 6px',
            'box-shadow: 0 4px 12px rgba(0,0,0,0.15)',
            'z-index: 10000',
            'animation: slideIn 0.3s ease',
        ].join(';');
        document.body.appendChild(el);

        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.3s ease';
            setTimeout(() => el.remove(), 300);
        }, 3000);
    }

    // ── Pending-Badge ────────────────────────────────────────────

    function updatePendingBadge() {
        const count = getQueueLength();
        const existing = document.querySelector('.' + PENDING_BADGE_CLASS);
        if (existing) existing.remove();

        if (count === 0) return;

        const badge = document.createElement('div');
        badge.className = PENDING_BADGE_CLASS;
        badge.textContent = '⏳ ' + count + ' Timer-Aktion' + (count > 1 ? 'en' : '') + ' ausstehend';
        badge.style.cssText = [
            'position: fixed',
            'bottom: 20px',
            'right: 20px',
            'padding: 10px 16px',
            'background: #f9e2af',
            'color: #1e1e2e',
            'border-radius: 8px',
            'box-shadow: 0 4px 12px rgba(0,0,0,0.15)',
            'z-index: 10001',
            'font-size: 14px',
            'animation: slideIn 0.3s ease',
            'cursor: pointer',
        ].join(';');
        badge.title = 'Klicken um sofort zu synchronisieren';
        badge.addEventListener('click', function() {
            processQueue();
        });
        document.body.appendChild(badge);
    }

    // ── Initialisierung & Reconciliation bei Seitenladung ────────

    function reconcileOnPageLoad() {
        const queue = getQueue();
        if (queue.length === 0) return;

        // Für jedes Profil mit pendenden Aktionen: Status holen und
        // lokalen State anpassen
        const profileIds = [...new Set(queue.map(i => i.profileId))];
        profileIds.forEach(pid => {
            fetchTimerStatus(pid).then(() => {
                // Nach Status-Update: überschüssige Queue-Einträge entfernen
                const pending = getPendingForProfile(pid);
                pending.forEach(item => {
                    // Hole frischen Status aus timers Map
                    const state = timers.get(pid);
                    if (!state) return;
                    if (!isActionValid(item.action, {
                        has_timer: state.hasTimer,
                        is_paused: state.isPaused,
                    })) {
                        removeFromQueue(item.id);
                    }
                });
                updatePendingBadge();
            });
        });
    }

    // ── Event-Binding ────────────────────────────────────────────

    function initTimerControls() {
        document.querySelectorAll('.timer-controls').forEach(controlsEl => {
            const profileId = controlsEl.getAttribute('data-profile-id');
            if (!profileId) return;

            controlsEl.addEventListener('click', function(e) {
                const btn = e.target.closest('[data-action]');
                if (!btn) return;

                const action = btn.getAttribute('data-action');

                if (action === 'stop') {
                    openStopModal(profileId);
                    return;
                }

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

    // ── Stop Modal ─────────────────────────────────────────────

    function openStopModal(profileId) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;

        // Fehler-Banner zurücksetzen
        hideStopError(profileId);

        // Frischen Server-Status holen, Modal erst DANN anzeigen
        // (vermeidet "leeres Modal" während des Server-Roundtrips)
        fetchTimerStatus(profileId).then(() => {
            const state = timers.get(profileId);
            if (!state || !state.hasTimer) {
                return; // kein Timer mehr, nichts zu tun
            }
            populateStopModal(profileId, state);

            // Jetzt erst anzeigen
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            // ESC-Handler
            modal._escHandler = function(e) {
                if (e.key === 'Escape') closeStopModal(profileId);
            };
            document.addEventListener('keydown', modal._escHandler);

            // Notiz-Feld fokussieren
            setTimeout(function() {
                const ta = modal.querySelector('[data-field="notes"]');
                if (ta) ta.focus();
            }, 80);
        }).catch(() => {
            // Server nicht erreichbar → Modal trotzdem zeigen mit Hinweis
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            showStopError(profileId, 'Status konnte nicht geladen werden. Notiz wird trotzdem gespeichert.');
        });
    }

    function closeStopModal(profileId) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;
        modal.style.display = 'none';
        document.body.style.overflow = '';
        if (modal._escHandler) {
            document.removeEventListener('keydown', modal._escHandler);
            modal._escHandler = null;
        }
        hideStopError(profileId);
        // Confirm-Button re-enable
        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) confirmBtn.disabled = false;
    }

    function populateStopModal(profileId, state) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;

        const startTime = new Date(state.start_time);
        const now = new Date();

        // pausierte Sekunden aus Modal-Dataset (vom Server-Status gesetzt)
        const pausedSeconds = parseInt(modal.dataset.pausedSeconds || '0', 10) || 0;

        // Effektive End-Zeit:
        // - Wenn pausiert: startTime + (elapsed + paused) Sekunden
        // - Sonst: jetzt
        let effectiveEnd;
        if (state.is_paused) {
            const elapsed = state.elapsedSeconds || 0;
            effectiveEnd = new Date(startTime.getTime() + (elapsed + pausedSeconds) * 1000);
        } else {
            effectiveEnd = now;
        }

        // Anzeige
        const dateOpts = { year: 'numeric', month: '2-digit', day: '2-digit' };
        const timeOpts = { hour: '2-digit', minute: '2-digit' };
        const userLocale = (navigator.language || 'de-DE');

        modal.querySelector('[data-field="display_date"]').textContent =
            startTime.toLocaleDateString(userLocale, dateOpts);
        modal.querySelector('[data-field="display_start"]').textContent =
            startTime.toLocaleTimeString(userLocale, timeOpts);
        modal.querySelector('[data-field="display_end"]').textContent =
            effectiveEnd.toLocaleTimeString(userLocale, timeOpts);

        const totalSeconds = (effectiveEnd - startTime) / 1000;
        const workSeconds = Math.max(0, totalSeconds - pausedSeconds);
        const hours = (workSeconds / 3600).toFixed(2);
        const pauseHours = (pausedSeconds / 3600).toFixed(2);

        modal.querySelector('[data-field="display_pause"]').textContent = pauseHours;
        modal.querySelector('[data-field="display_hours"]').textContent = hours;

        // Editierbare Felder mit Defaults füllen (nur wenn can_edit)
        if (modal.dataset.canEdit === 'true') {
            const dateInput = modal.querySelector('[data-field="date"]');
            const startInput = modal.querySelector('[data-field="start_time"]');
            const endInput = modal.querySelector('[data-field="end_time"]');
            const pauseInput = modal.querySelector('[data-field="pause_duration"]');

            if (dateInput) {
                const y = startTime.getFullYear();
                const m = String(startTime.getMonth() + 1).padStart(2, '0');
                const d = String(startTime.getDate()).padStart(2, '0');
                dateInput.value = y + '-' + m + '-' + d;
            }
            if (startInput) {
                startInput.value = startTime.toTimeString().slice(0, 5);
            }
            if (endInput) {
                endInput.value = effectiveEnd.toTimeString().slice(0, 5);
            }
            if (pauseInput) {
                pauseInput.value = pauseHours;
            }
        }
    }

    function confirmStop(profileId) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;

        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn && confirmBtn.disabled) return;
        if (confirmBtn) confirmBtn.disabled = true;

        const payload = {
            notes: (modal.querySelector('[data-field="notes"]').value || '').slice(0, 1000)
        };

        if (modal.dataset.canEdit === 'true') {
            const dateVal = modal.querySelector('[data-field="date"]').value;
            const startVal = modal.querySelector('[data-field="start_time"]').value;
            const endVal = modal.querySelector('[data-field="end_time"]').value;
            const pauseVal = modal.querySelector('[data-field="pause_duration"]').value;

            if (dateVal) payload.date = dateVal;
            if (startVal) payload.start_time = startVal;
            if (endVal) payload.end_time = endVal;
            if (pauseVal !== '' && pauseVal !== null) {
                payload.pause_duration = parseFloat(pauseVal);
            }
        }

        // Optimistic state + queue (mit payload, damit Notiz gespeichert wird)
        applyOptimisticState(profileId, 'stop');
        enqueue(profileId, 'stop', payload);

        // Modal schließen
        closeStopModal(profileId);

        // Notification
        const noteInfo = payload.notes ? ' – Notiz gespeichert' : '';
        showNotification('Timer gestoppt' + noteInfo, 'success');
    }

    function showStopError(profileId, message) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;
        const errorEl = modal.querySelector('.stop-error');
        if (!errorEl) return;
        errorEl.textContent = message;
        errorEl.style.display = 'block';
        // Confirm-Button re-enable
        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) confirmBtn.disabled = false;
    }

    function hideStopError(profileId) {
        const modal = document.getElementById('stop-modal-' + profileId);
        if (!modal) return;
        const errorEl = modal.querySelector('.stop-error');
        if (!errorEl) return;
        errorEl.textContent = '';
        errorEl.style.display = 'none';
    }

    function initStopModals() {
        document.querySelectorAll('.stop-overlay').forEach(function(modal) {
            const profileId = modal.getAttribute('data-profile-id');
            if (!profileId) return;

            const cancelBtn = modal.querySelector('[data-action="cancel"]');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', function() {
                    closeStopModal(profileId);
                });
            }

            const confirmBtn = modal.querySelector('[data-action="confirm"]');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', function() {
                    confirmStop(profileId);
                });
            }

            // Klick auf Overlay (außerhalb des Modals) → schließen
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    closeStopModal(profileId);
                }
            });
        });
    }

    // ── Periodische Jobs ─────────────────────────────────────────

    // Sekündliches UI-Update für laufende Timer
    setInterval(() => {
        timers.forEach((td, pid) => {
            if (td.hasTimer && !td.isPaused && td.lastUpdate > 0) {
                updateTimerDisplay(pid);
            }
        });
    }, 1000);

    // Server-Poll (alle 5s) — nur wenn Timer aktiv
    setInterval(() => {
        const hasActive = Array.from(timers.values()).some(t => t.hasTimer);
        if (hasActive) {
            timers.forEach((_, pid) => fetchTimerStatus(pid));
        }
    }, POLL_INTERVAL);

    // Queue-Verarbeitung (alle 10s)
    setInterval(processQueue, QUEUE_PERIODIC);

    // Bei Rückkehr aus Offline-Modus sofort Queue verarbeiten
    window.addEventListener('online', processQueue);

    // DOM Ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initTimerControls();
            initAllTimers();
            initStopModals();
            reconcileOnPageLoad();
            updatePendingBadge();
        });
    } else {
        initTimerControls();
        initAllTimers();
        initStopModals();
        reconcileOnPageLoad();
        updatePendingBadge();
    }

})();
