const configuredApiBase = typeof window.PARKME_API_BASE === 'string'
    ? window.PARKME_API_BASE.trim()
    : '';
const isFirebaseHostedOrigin = window.location.hostname.endsWith('.web.app') ||
    window.location.hostname.endsWith('.firebaseapp.com');
const API_BASE = configuredApiBase
    ? configuredApiBase.replace(/\/$/, '')
    : isFirebaseHostedOrigin
        ? 'https://YOUR_CLOUD_RUN_URL/api/v1'
        : `${window.location.origin}/api/v1`;
const BACKEND_ORIGIN = API_BASE.replace(/\/api\/v1$/, '');
const SPOT_STALE_MS = 120000;
const STATS_REFRESH_INTERVAL_MS = 60000;
const SPOT_DYNAMIC_REFRESH_INTERVAL_MS = 2000;
const RESOLVED_PLATE = 'RESOLVED';
const REJECTED_PLATE = 'REJECTED';
const MANUAL_ACCEPTED_PLATE = 'MANUAL_ACCEPTED';

// Initialize Firebase
if (typeof firebase !== 'undefined') {
    if (firebase.apps.length === 0) {
        // Fallback for local development (e.g. running via FastAPI port 8000)
        // Replace with your Firebase Web Config from Project Settings in Firebase Console
        const firebaseConfig = {
            apiKey: "AIzaSyCWJYe7NQ0G9c44XjjXKSGAIEx1bQD2jxI",
            authDomain: "parkme-technion-f280b.firebaseapp.com",
            projectId: "parkme-technion-f280b",
            storageBucket: "parkme-technion-f280b.firebasestorage.app",
            messagingSenderId: "31114651685",
            appId: "1:31114651685:web:1281f3fbd87a6fc078f7cc",
            measurementId: "G-9CLBFRBMD5"
        };
        firebase.initializeApp(firebaseConfig);
    }
}

// DOM Elements
const loginScreen = document.getElementById('login-screen');
const dashboardScreen = document.getElementById('dashboard-screen');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const adminPanel = document.getElementById('admin-panel');
const dashboardLayout = document.querySelector('.dashboard-layout');
const spotsGrid = document.getElementById('spots-grid');
const recommendationBanner = document.getElementById('recommendation-banner');
const securityLogs = document.getElementById('security-logs');
const statsGrid = document.getElementById('stats-grid');
const logoutBtn = document.getElementById('logout-btn');

let eventSource = null;
let currentProfile = null;
let statsRefreshInterval = null;
let spotHealthInterval = null;
const currentSpots = new Map();
const offlineSpotIds = new Set();
const pendingReviewSpotIds = new Set();

function showLoginErrorMessage(message) {
    loginError.textContent = message;
    loginError.classList.remove('hidden');
}

function hideLoginErrorMessage() {
    loginError.classList.add('hidden');
}

// Parse JWT utility
function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(window.atob(base64));
    } catch (e) {
        return null;
    }
}

// Show Toast Notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function stopStatsRefresh() {
    if (statsRefreshInterval) {
        clearInterval(statsRefreshInterval);
        statsRefreshInterval = null;
    }
}

function startStatsRefresh() {
    stopStatsRefresh();
    statsRefreshInterval = setInterval(() => {
        if (currentProfile && currentProfile.role === 'admin') {
            fetchStats();
            syncOfflineState();
        }
    }, STATS_REFRESH_INTERVAL_MS);
}

function stopSpotHealthMonitor() {
    if (spotHealthInterval) {
        clearInterval(spotHealthInterval);
        spotHealthInterval = null;
    }
}

function startSpotHealthMonitor() {
    stopSpotHealthMonitor();
    spotHealthInterval = setInterval(() => {
        syncOfflineState();
        refreshDynamicSpotCards();
    }, SPOT_DYNAMIC_REFRESH_INTERVAL_MS);
}

function isSpotOffline(spot) {
    if (!spot || !spot.last_seen) {
        return false;
    }
    const lastSeenMs = new Date(spot.last_seen).getTime();
    if (Number.isNaN(lastSeenMs)) {
        return false;
    }
    return Date.now() - lastSeenMs > SPOT_STALE_MS;
}

function renderStats(stats) {
    if (!statsGrid) {
        return;
    }

    const items = [
        {
            label: 'Occupied Now',
            value: `${stats.occupied_spots}/${stats.total_spots}`,
            meta: 'Current live occupancy'
        },
        {
            label: 'Authorized Sessions',
            value: stats.authorized_sessions ?? 0,
            meta: `Peak hour ${stats.peak_hour || 'N/A'}`
        },
        {
            label: 'Violations',
            value: stats.violation_events ?? 0,
            meta: `Unresolved ${stats.unresolved_events ?? 0}`
        },
        {
            label: 'Parking Logs',
            value: stats.total_logs ?? 0,
            meta: `Busiest spot ${stats.busiest_spot || 'N/A'}`
        },
        {
            label: 'Avg Duration',
            value: stats.average_duration_minutes !== null && stats.average_duration_minutes !== undefined
                ? `${stats.average_duration_minutes}m`
                : 'N/A',
            meta: `Aborted ${stats.aborted_events ?? 0} | Resolved ${stats.resolved_events ?? 0}`
        }
    ];

    statsGrid.innerHTML = items.map((item) => `
        <div class="stat-card">
            <div class="stat-label">${item.label}</div>
            <div class="stat-value">${item.value}</div>
            <div class="stat-meta">${item.meta}</div>
        </div>
    `).join('');
}

function syncOfflineState() {
    currentSpots.forEach((spot, spotId) => {
        const offline = isSpotOffline(spot);
        const wasOffline = offlineSpotIds.has(spotId);

        if (offline && !wasOffline) {
            offlineSpotIds.add(spotId);
            if (currentProfile && currentProfile.role === 'admin') {
                showToast(`Sensor at Spot ${spotId} looks offline. Last heartbeat is older than 2 minutes.`, 'warning');
            }
            updateSpotUI(spot);
            return;
        }

        if (!offline && wasOffline) {
            offlineSpotIds.delete(spotId);
            if (currentProfile && currentProfile.role === 'admin') {
                showToast(`Sensor at Spot ${spotId} is back online.`, 'info');
            }
            updateSpotUI(spot);
        }
    });
    renderRecommendation();
}

function renderRecommendation() {
    if (!recommendationBanner) {
        return;
    }

    const visibleFreeSpots = Array.from(currentSpots.values())
        .filter((spot) => !spot.is_occupied && !isSpotOffline(spot))
        .sort((a, b) => a.id.localeCompare(b.id));

    if (visibleFreeSpots.length === 0) {
        recommendationBanner.classList.remove('hidden');
        recommendationBanner.textContent = 'No verified free spots are available right now. Please wait for the next live update.';
        return;
    }

    const recommendedSpot = visibleFreeSpots[0];
    recommendationBanner.classList.remove('hidden');
    recommendationBanner.textContent = `Recommended spot right now: ${recommendedSpot.id} (${recommendedSpot.category}).`;
}

function toBackendAssetUrl(path) {
    if (!path) {
        return null;
    }
    if (/^https?:\/\//i.test(path)) {
        return path;
    }
    return `${BACKEND_ORIGIN}${path}`;
}

function getReviewResolveAfterMs(spot) {
    if (!spot || !spot.review_resolve_after) {
        return null;
    }
    const resolveAfterMs = new Date(spot.review_resolve_after).getTime();
    return Number.isNaN(resolveAfterMs) ? null : resolveAfterMs;
}

function canResolveMissingCapture(spot) {
    if (!spot || !spot.is_occupied || spot.license_plate !== 'UNIDENTIFIED' || spot.review_capture_url) {
        return false;
    }
    const resolveAfterMs = getReviewResolveAfterMs(spot);
    return resolveAfterMs !== null && Date.now() >= resolveAfterMs;
}

function getUnidentifiedReviewNote(spot, hasCapture) {
    if (hasCapture) {
        return 'Plate could not be read. Review the latest photo and accept or reject this vehicle.';
    }
    if (canResolveMissingCapture(spot)) {
        return 'No camera image arrived in time. Accept or reject this vehicle manually.';
    }
    return 'Waiting for the camera image. You can already accept or reject manually.';
}

function refreshDynamicSpotCards() {
    currentSpots.forEach((spot) => {
        if (
            spot &&
            !pendingReviewSpotIds.has(spot.id) &&
            (spot.license_plate === 'UNIDENTIFIED' || spot.license_plate === REJECTED_PLATE)
        ) {
            updateSpotUI(spot);
        }
    });
}

// Authentication
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    try {
        if (typeof firebase === 'undefined' || !firebase.auth) {
            throw new Error('Firebase Auth SDK not loaded. If running locally, make sure you configure your Firebase credentials.');
        }

        // Authenticate directly with Firebase Auth
        const userCredential = await firebase.auth().signInWithEmailAndPassword(email, password);
        const token = await userCredential.user.getIdToken();
        
        localStorage.setItem('parkme_token', token);
        hideLoginErrorMessage();
        initDashboard();
    } catch (error) {
        showLoginErrorMessage(error.message);
    }
});

logoutBtn.addEventListener('click', () => {
    if (typeof firebase !== 'undefined' && firebase.auth) {
        firebase.auth().signOut().catch(console.error);
    }
    currentProfile = null;
    currentSpots.clear();
    offlineSpotIds.clear();
    stopStatsRefresh();
    stopSpotHealthMonitor();
    localStorage.removeItem('parkme_profile');
    localStorage.removeItem('parkme_token');
    if (eventSource) eventSource.close();
    dashboardScreen.classList.add('hidden');
    loginScreen.classList.remove('hidden');
    if (statsGrid) {
        statsGrid.innerHTML = '';
    }
    if (recommendationBanner) {
        recommendationBanner.classList.add('hidden');
        recommendationBanner.textContent = '';
    }
});

// Initialize Dashboard
async function initDashboard() {
    const token = localStorage.getItem('parkme_token');
    if (!token) return;

    try {
        // Fetch current user details from backend using Firebase token
        const res = await fetch(`${API_BASE}/users/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) {
            throw new Error('Failed to fetch user profile');
        }
        const profile = await res.json();
        currentProfile = profile;
        localStorage.setItem('parkme_profile', JSON.stringify(profile));

        // UI Updates
        document.getElementById('user-greeting').textContent = `Welcome, ${profile.name}`;
        let roleText = profile.role;
        if (profile.is_special_needs) {
            roleText += ' (Special Needs)';
        }
        document.getElementById('user-role-badge').textContent = roleText;

        loginScreen.classList.add('hidden');
        dashboardScreen.classList.remove('hidden');

        if (profile.role === 'admin') {
            adminPanel.classList.remove('hidden');
            dashboardLayout.classList.add('has-admin');
            fetchLogs();
            fetchStats();
            startStatsRefresh();
        } else {
            adminPanel.classList.add('hidden');
            dashboardLayout.classList.remove('has-admin');
            stopStatsRefresh();
            if (statsGrid) {
                statsGrid.innerHTML = '';
            }
        }

        startSpotHealthMonitor();

        // Connect SSE
        connectSSE(token);
        
        // Fetch spots
        fetchSpots();
    } catch (e) {
        console.error("Dashboard initialization failed:", e);
        // Clean up token and show login screen if authentication fails
        currentProfile = null;
        currentSpots.clear();
        offlineSpotIds.clear();
        stopStatsRefresh();
        stopSpotHealthMonitor();
        localStorage.removeItem('parkme_profile');
        localStorage.removeItem('parkme_token');
        loginScreen.classList.remove('hidden');
        dashboardScreen.classList.add('hidden');
        showLoginErrorMessage('Authenticated, but could not reach the backend API. Please verify the backend URL and try again.');
    }
}

function connectSSE(token) {
    // Attempting to connect to SSE (Endpoint to be implemented on backend)
    try {
        eventSource = new EventSource(`${API_BASE}/stream?token=${token}`);
        
        eventSource.onopen = () => {
            document.getElementById('connection-status').style.background = 'var(--status-free)';
        };

        eventSource.onerror = () => {
            document.getElementById('connection-status').style.background = 'var(--status-violation)';
            console.error("SSE Connection issue (Likely because backend /api/v1/stream is not built yet)");
        };

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'spot_update') {
                updateSpotUI(data.spot);
                syncOfflineState();
            } else if (data.type === 'log_event') {
                appendLog(data.log);
                if (currentProfile && currentProfile.role === 'admin') {
                    fetchStats();
                }
            } else if (data.type === 'log_aborted') {
                const logItem = document.getElementById(`log-item-${data.log_id}`);
                if (logItem) {
                    const actionDiv = logItem.querySelector('.log-action');
                    if (actionDiv) {
                        actionDiv.remove();
                    }
                    const msgSpan = logItem.querySelector('.log-message');
                    if (msgSpan) {
                        msgSpan.className = 'log-message';
                        msgSpan.textContent = `Driver aborted parking at Spot ${data.spot_id}.`;
                    }
                }
            }
        };
    } catch (e) {
        console.log("SSE Init Error", e);
    }
}

function setReviewButtonsPending(spotId, label) {
    pendingReviewSpotIds.add(spotId);
    document.querySelectorAll(`[data-review-spot="${spotId}"]`).forEach((button) => {
        button.disabled = true;
        button.style.opacity = '0.5';
        button.style.cursor = 'wait';
        button.innerText = label;
    });
}

async function submitSpotReview(spotId, action) {
    const token = localStorage.getItem('parkme_token');
    const isReject = action === 'reject';
    setReviewButtonsPending(
        spotId,
        isReject ? 'Rejecting...' : 'Accepting...'
    );
    try {
        const res = await fetch(`${API_BASE}/sensors/${action}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ spot_id: spotId })
        });
        
        if (res.ok) {
            const existingSpot = currentSpots.get(spotId);
            if (existingSpot) {
                updateSpotUI({
                    ...existingSpot,
                    is_occupied: true,
                    license_plate: isReject ? REJECTED_PLATE : MANUAL_ACCEPTED_PLATE,
                    is_violation: isReject,
                    review_capture_url: isReject ? existingSpot.review_capture_url : null,
                    review_status: null,
                    review_resolve_after: null
                });
            } else {
                fetchSpots();
            }
            showToast(
                isReject
                    ? `Spot ${spotId} rejected successfully.`
                    : `Spot ${spotId} accepted successfully.`,
                isReject ? 'warning' : 'info'
            );
            fetchLogs();
            fetchStats();
        } else {
            let detail = isReject
                ? `Failed to reject Spot ${spotId}. Please try again.`
                : `Failed to accept Spot ${spotId}. Please try again.`;
            try {
                const errorData = await res.json();
                if (errorData && errorData.detail) {
                    detail = errorData.detail;
                }
            } catch (e) {
                // Leave the fallback message if the error response is not JSON.
            }
            showToast(detail, 'warning');
            fetchSpots();
        }
    } catch (e) {
        showToast(
            isReject
                ? `Could not reach the backend to reject Spot ${spotId}.`
                : `Could not reach the backend to accept Spot ${spotId}.`,
            'warning'
        );
        fetchSpots();
    } finally {
        pendingReviewSpotIds.delete(spotId);
    }
}

async function acceptSpot(spotId) {
    return submitSpotReview(spotId, 'accept');
}

async function rejectSpot(spotId) {
    return submitSpotReview(spotId, 'reject');
}

async function fetchStats() {
    const token = localStorage.getItem('parkme_token');
    if (!token || !currentProfile || currentProfile.role !== 'admin') {
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/admin/usage-stats`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!res.ok) {
            throw new Error('Failed to fetch usage stats');
        }

        const stats = await res.json();
        renderStats(stats);
    } catch (e) {
        console.error("Failed to fetch stats", e);
    }
}

// Rendering Logic
function createSpotCard(spot) {
    const div = document.createElement('div');
    const offline = isSpotOffline(spot);
    
    let statusClass = 'free';
    let plateDisplay = 'EMPTY';
    
    if (offline) {
        statusClass = 'offline';
        plateDisplay = 'OFFLINE';
    } else if (spot.is_occupied) {
        if (spot.is_violation && spot.license_plate === 'UNIDENTIFIED') {
            statusClass = 'unidentified';
            plateDisplay = '⚠️ UNIDENTIFIED';
        } else if (spot.license_plate === RESOLVED_PLATE) {
            statusClass = 'free';
            plateDisplay = 'EMPTY';
        } else if (spot.license_plate === MANUAL_ACCEPTED_PLATE) {
            statusClass = 'occupied';
            plateDisplay = 'OCCUPIED (ADMIN ACCEPTED)';
        } else if (spot.license_plate === REJECTED_PLATE) {
            statusClass = 'violation';
            plateDisplay = 'OCCUPIED (REJECTED)';
        } else if (spot.is_violation) {
            statusClass = 'violation';
            plateDisplay = spot.license_plate;
        } else {
            statusClass = 'occupied';
            plateDisplay = spot.license_plate || 'TAKEN';
        }
    }

    div.className = `spot-card ${statusClass}`;
    div.id = `spot-${spot.id}`;

    let html = `
        <div class="spot-header">
            <span class="spot-id">${spot.id}</span>
            <span class="spot-category">${spot.category}</span>
        </div>
        <div class="spot-body">
            <div class="plate-number">${plateDisplay}</div>
        </div>
    `;

    const profile = currentProfile ||
        (() => {
            try {
                return JSON.parse(localStorage.getItem('parkme_profile'));
            } catch (e) {
                return null;
            }
        })();
    if (profile && profile.role === 'admin') {
        let batt = spot.battery_level !== undefined && spot.battery_level !== null ? `${spot.battery_level}%` : 'N/A';
        let seen = spot.last_seen ? new Date(spot.last_seen).toLocaleTimeString('en-US', { timeZone: 'Asia/Jerusalem' }) : 'N/A';
        html += `
            <div style="font-size: 0.8rem; color: #888; margin-top: 10px; border-top: 1px solid #333; padding-top: 5px;">
                <div>🔋 Battery: ${batt}</div>
                <div>📡 Ping: ${seen}</div>
            </div>
        `;
        if (offline) {
            html += `<div class="device-status offline-text">No heartbeat received in the last 2 minutes.</div>`;
        }
        if (statusClass === 'unidentified') {
            const reviewCaptureUrl = toBackendAssetUrl(spot.review_capture_url);

            if (reviewCaptureUrl) {
                html += `
                    <div class="review-preview">
                        <div class="review-label">Latest camera image</div>
                        <img src="${reviewCaptureUrl}" alt="Latest camera image for spot ${spot.id}" class="review-image">
                    </div>
                `;
            } else {
                html += `<div class="device-status review-note">No camera image is available yet.</div>`;
            }
            html += `<div class="device-status review-note">${getUnidentifiedReviewNote(spot, Boolean(reviewCaptureUrl))}</div>`;
            html += `
                <div class="review-actions">
                    <button class="accept-btn review-btn" data-review-spot="${spot.id}" onclick="acceptSpot('${spot.id}')">Accept Vehicle</button>
                    <button class="reject-btn review-btn" data-review-spot="${spot.id}" onclick="rejectSpot('${spot.id}')">Reject Vehicle</button>
                </div>
            `;
        } else if (spot.license_plate === REJECTED_PLATE) {
            const reviewCaptureUrl = toBackendAssetUrl(spot.review_capture_url);
            if (reviewCaptureUrl) {
                html += `
                    <div class="review-preview">
                        <div class="review-label">Latest camera image</div>
                        <img src="${reviewCaptureUrl}" alt="Rejected vehicle image for spot ${spot.id}" class="review-image">
                    </div>
                `;
            }
            html += `<div class="device-status review-note">Rejected by admin. This spot will clear automatically once the car leaves.</div>`;
        }
    } else if (offline) {
        html += `<div class="device-status offline-text">Temporarily unavailable.</div>`;
    }

    div.innerHTML = html;
    return div;
}

function updateSpotUI(spot) {
    currentSpots.set(spot.id, spot);
    const existing = document.getElementById(`spot-${spot.id}`);

    const newCard = createSpotCard(spot);
    if (existing) {
        existing.replaceWith(newCard);
    } else {
        spotsGrid.appendChild(newCard);
    }
    renderRecommendation();
}

function appendLog(log) {
    const li = document.createElement('li');
    li.className = 'log-item';
    if (log.log_id) {
        li.id = `log-item-${log.log_id}`;
    }
    
    const time = new Date(log.timestamp).toLocaleTimeString('en-US', { timeZone: 'Asia/Jerusalem' });
    let msgClass = '';
    
    if (log.type === 'violation') msgClass = 'violation';
    if (log.type === 'unidentified') msgClass = 'unidentified';

    li.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message ${msgClass}">${log.message}</span>
    `;

    if (log.type === 'violation' && log.log_id) {
        const btnContainer = document.createElement('div');
        btnContainer.className = 'log-action';
        btnContainer.innerHTML = `<button class="btn-secondary btn-small" onclick="showViolationPicture('${log.log_id}', this)">Show Picture</button>`;
        li.appendChild(btnContainer);
    }

    securityLogs.prepend(li);
}

async function showViolationPicture(logId, btnElement) {
    const container = btnElement.parentElement;
    const token = localStorage.getItem('parkme_token');
    try {
        btnElement.innerText = "Loading...";
        btnElement.disabled = true;
        const res = await fetch(`${API_BASE}/logs/${logId}/capture`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        if (!res.ok) throw new Error("Image not found");
        
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        
        container.innerHTML = `<img src="${url}" class="violation-capture-img" alt="Violation Capture" />`;
    } catch (e) {
        btnElement.innerText = "Error loading";
    }
}

// Initial fetch
async function fetchSpots() {
    const token = localStorage.getItem('parkme_token');
    try {
        const res = await fetch(`${API_BASE}/spots`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!res.ok) throw new Error('Failed to fetch spots');
        
        const data = await res.json();
        
        currentSpots.clear();
        offlineSpotIds.clear();
        spotsGrid.innerHTML = '';
        data.spots.forEach(updateSpotUI);
        syncOfflineState();
    } catch (e) {
        console.error("Failed to fetch initial spots", e);
    }
}

async function fetchLogs() {
    const token = localStorage.getItem('parkme_token');
    try {
        const res = await fetch(`${API_BASE}/logs`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!res.ok) throw new Error('Failed to fetch logs');
        
        const data = await res.json();
        
        securityLogs.innerHTML = '';
        // Because they are DESC from backend, we append them reversed to prepend
        data.logs.reverse().forEach(log => appendLog(log));
    } catch (e) {
        console.error("Failed to fetch logs", e);
    }
}

// Auto-login check
const savedToken = localStorage.getItem('parkme_token');
if (savedToken) {
    const payload = parseJwt(savedToken);
    if (payload && payload.exp && payload.exp * 1000 > Date.now()) {
        initDashboard();
    } else {
        localStorage.removeItem('parkme_token');
    }
}
