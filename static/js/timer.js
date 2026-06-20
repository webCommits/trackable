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
    let queueProcessing = false;        // Schutz gegen parallele Queue-Läufe
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

    function enqueue(profileId, action, payload, clientTimestamp) {
        const queue = getQueue();
        queue.push({
            id: generateId(),
            profileId: profileId,
            action: action,
            clientTimestamp: clientTimestamp || new Date().toISOString(),
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
        if (queueProcessing) {
            updatePendingBadge();
            return;
        }
        queueProcessing = true;
        try {
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
        } finally {
            queueProcessing = false;
            updatePendingBadge();
        }
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
            // Stop-Validierungsfehler VOR generischem 400 behandeln
            if (resp.status === 400 && item.action === 'stop') {
                try {
                    showStopError(item.profileId, data.error || 'Validierungsfehler');
                } catch (e) { /* Modal existiert evtl. nicht mehr */ }
                fetchTimerStatus(item.profileId);
                return true; // aus Queue entfernen, User muss erneut bestätigen
            }
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
                    startTime: data.start_time,
                    totalPausedSeconds: 0,
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
                        td.totalPausedSeconds = data.total_paused_seconds || td.totalPausedSeconds || 0;
                        td.lastUpdate = now;
                        timers.set(profileId, td);
                    }
                }
                break;

            case 'resume':
                {
                    const td = timers.get(profileId);
                    if (td && td.isPaused) {
                        td.isPaused = false;
                        td.totalPausedSeconds = data.total_paused_seconds || td.totalPausedSeconds || 0;
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
                    startTime: new Date().toISOString(),
                    totalPausedSeconds: 0,
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
                    // start_time und totalPausedSeconds für Stop-Modal einfrieren
                    startTime: data.start_time,
                    totalPausedSeconds: data.total_paused_seconds || 0,
                });
                // pausedSeconds ins Modal-Dataset schreiben für populateStopModal
                const modal = getStopModal();
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
                // Keine Queue-Einträge beim Page-Load löschen: Eine gültige
                // Offline-Sequenz wie start→stop kann aus Sicht des aktuellen
                // Serverstatus teilweise ungültig aussehen. Die FIFO-
                // Verarbeitung in processQueueItem entscheidet später mit
                // frischem Status pro Aktion.
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
    //
    // Es gibt genau EIN #stop-modal-Element im Template, ausserhalb der
    // .card-Container. Ohne diese Trennung wuerde position:fixed bei
    // :hover-transformierten Vorfahren (.card:hover{transform:...}) zu
    // position:absolute kollabieren → das Modal waere in der Kachel
    // gefangen statt zentral zu erscheinen.

    function getStopModal() {
        return document.getElementById('stop-modal');
    }

    function getActiveStopProfileId() {
        const m = getStopModal();
        return m ? m.getAttribute('data-profile-id') || null : null;
    }

    function openStopModal(profileId) {
        const modal = getStopModal();
        if (!modal) return;

        // Profil-Kontext setzen
        modal.setAttribute('data-profile-id', String(profileId));

        // Titel mit Profil-Name aktualisieren
        const titleEl = modal.querySelector('#stop-modal-title');
        const controls = document.querySelector(
            '.timer-controls[data-profile-id="' + profileId + '"]'
        );
        const profileTitle = controls
            ? controls.getAttribute('data-profile-title') || ''
            : '';
        if (titleEl) {
            const baseTitle = (titleEl.getAttribute('data-base-title') || titleEl.textContent || '').trim();
            if (profileTitle && !titleEl.getAttribute('data-base-title')) {
                titleEl.setAttribute('data-base-title', baseTitle);
            }
            titleEl.textContent = baseTitle + (profileTitle ? ' \u2013 ' + profileTitle : '');
        }

        // Fehler-Banner zurücksetzen
        hideStopError();

        // Frischen Server-Status holen, Modal erst DANN anzeigen
        fetchTimerStatus(profileId).then(() => {
            const state = timers.get(profileId);
            if (!state || !state.hasTimer) {
                showNotification('Kein aktiver Timer gefunden.', 'error');
                return; // kein Timer mehr
            }
            // Stop-Zeitpunkt einfrieren: aktueller Moment als FrozenTimestamp
            const frozenTimestamp = new Date().toISOString();
            modal.dataset.frozenTimestamp = frozenTimestamp;
            const populated = populateStopModal(state, frozenTimestamp);
            const confirmBtn = modal.querySelector('[data-action="confirm"]');
            if (confirmBtn) confirmBtn.disabled = !populated;

            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';

            setTimeout(function() {
                const ta = modal.querySelector('[data-field="notes"]');
                if (ta) ta.focus();
            }, 80);
        }).catch(() => {
            // Server nicht erreichbar → Modal trotzdem zeigen
            const frozenTimestamp = new Date().toISOString();
            modal.dataset.frozenTimestamp = frozenTimestamp;
            const state = timers.get(profileId);
            const confirmBtn = modal.querySelector('[data-action="confirm"]');
            if (state && state.hasTimer) {
                // Lokaler State vorhanden → Modal mit eingefrorenen Werten füllen.
                // Nur bei erfolgreich befülltem Modal bleibt Confirm aktiv
                // (Offline-Stop möglich).
                const populated = populateStopModal(state, frozenTimestamp);
                if (confirmBtn) confirmBtn.disabled = !populated;
                if (!populated) {
                    showStopError('Status konnte nicht geladen werden; bitte Verbindung prüfen und erneut versuchen.');
                }
                modal.style.display = 'flex';
                document.body.style.overflow = 'hidden';
            } else {
                // Kein lokaler State → Confirm deaktivieren, Fehler anzeigen
                if (confirmBtn) confirmBtn.disabled = true;
                showStopError('Status konnte nicht geladen werden; bitte Verbindung prüfen und erneut versuchen.');
                modal.style.display = 'flex';
                document.body.style.overflow = 'hidden';
            }
        });
    }

    function closeStopModal() {
        const modal = getStopModal();
        if (!modal) return;
        modal.style.display = 'none';
        document.body.style.overflow = '';
        modal.setAttribute('data-profile-id', '');
        modal.dataset.frozenTimestamp = '';
        modal.dataset.pausedSeconds = '0';
        hideStopError();
        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) confirmBtn.disabled = false;
        // Notiz + Override-Felder leeren, damit der naechste Aufruf frisch startet
        const ta = modal.querySelector('[data-field="notes"]');
        if (ta) ta.value = '';
        ['date', 'start_time', 'end_time', 'pause_duration'].forEach(function(f) {
            const el = modal.querySelector('[data-field="' + f + '"]');
            if (el) el.value = '';
        });
    }

    function populateStopModal(state, frozenTimestamp) {
        const modal = getStopModal();
        if (!modal) return false;

        const rawStartTime = state.startTime || state.start_time;
        const startTime = new Date(rawStartTime);
        if (!rawStartTime || Number.isNaN(startTime.getTime())) {
            showStopError('Startzeit konnte nicht gelesen werden. Bitte erneut versuchen.');
            return false;
        }
        // Verwende eingefrorenen Zeitstempel statt now() für konsistente Werte
        const now = frozenTimestamp ? new Date(frozenTimestamp) : new Date();

        const pausedSeconds = parseInt(
            state.totalPausedSeconds ?? modal.dataset.pausedSeconds ?? '0',
            10
        ) || 0;

        let effectiveEnd;
        if (state.isPaused) {
            const elapsed = state.elapsedSeconds || 0;
            effectiveEnd = new Date(startTime.getTime() + (elapsed + pausedSeconds) * 1000);
        } else {
            effectiveEnd = now;
        }

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
            if (startInput) startInput.value = startTime.toTimeString().slice(0, 5);
            if (endInput) endInput.value = effectiveEnd.toTimeString().slice(0, 5);
            if (pauseInput) pauseInput.value = pauseHours;
        }

        return true;
    }

    function confirmStop() {
        const modal = getStopModal();
        if (!modal) return;
        const profileId = getActiveStopProfileId();
        if (!profileId) return;

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

        applyOptimisticState(profileId, 'stop');
        // Verwende eingefrorenen Zeitstempel aus dem Modal
        const frozenTs = modal.dataset.frozenTimestamp;
        enqueue(profileId, 'stop', payload, frozenTs);
        closeStopModal();

        const noteInfo = payload.notes ? ' – Notiz gespeichert' : '';
        showNotification('Timer gestoppt' + noteInfo, 'success');
    }

    function showStopError(message) {
        const modal = getStopModal();
        if (!modal) return;
        const errorEl = modal.querySelector('.stop-error');
        if (!errorEl) return;
        errorEl.textContent = message;
        errorEl.style.display = 'block';
        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) confirmBtn.disabled = false;
    }

    function hideStopError() {
        const modal = getStopModal();
        if (!modal) return;
        const errorEl = modal.querySelector('.stop-error');
        if (!errorEl) return;
        errorEl.textContent = '';
        errorEl.style.display = 'none';
    }

    function initStopModals() {
        const modal = getStopModal();
        if (!modal) return;

        const cancelBtn = modal.querySelector('[data-action="cancel"]');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeStopModal);
        }

        const confirmBtn = modal.querySelector('[data-action="confirm"]');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', confirmStop);
        }

        // Klick auf Overlay (ausserhalb des .stop-modal) → schliessen
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeStopModal();
            }
        });

        // ESC schliesst (einmalig pro Modal registriert)
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                closeStopModal();
            }
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
