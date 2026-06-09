const API_BASE = 'http://localhost:8000/api/v1';

// DOM Elements
const loginScreen = document.getElementById('login-screen');
const dashboardScreen = document.getElementById('dashboard-screen');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const adminPanel = document.getElementById('admin-panel');
const dashboardLayout = document.querySelector('.dashboard-layout');
const spotsGrid = document.getElementById('spots-grid');
const securityLogs = document.getElementById('security-logs');
const logoutBtn = document.getElementById('logout-btn');

let eventSource = null;

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

// Authentication
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (!res.ok) {
            throw new Error('Invalid credentials');
        }

        const data = await res.json();
        localStorage.setItem('parkme_token', data.access_token);
        
        loginError.classList.add('hidden');
        initDashboard();
        
    } catch (error) {
        loginError.classList.remove('hidden');
        loginError.textContent = error.message;
    }
});

logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('parkme_token');
    if (eventSource) eventSource.close();
    dashboardScreen.classList.add('hidden');
    loginScreen.classList.remove('hidden');
});

// Initialize Dashboard
function initDashboard() {
    const token = localStorage.getItem('parkme_token');
    if (!token) return;

    const payload = parseJwt(token);
    if (!payload) return;

    // UI Updates
    document.getElementById('user-greeting').textContent = `Welcome, ${payload.name}`;
    let roleText = payload.role;
    if (payload.is_special_needs) {
        roleText += ' (Special Needs)';
    }
    document.getElementById('user-role-badge').textContent = roleText;

    loginScreen.classList.add('hidden');
    dashboardScreen.classList.remove('hidden');

    if (payload.role === 'admin') {
        adminPanel.classList.remove('hidden');
        dashboardLayout.classList.add('has-admin');
        fetchLogs();
    } else {
        adminPanel.classList.add('hidden');
        dashboardLayout.classList.remove('has-admin');
    }

    // Connect SSE
    connectSSE(token);
    
    // Fetch initial spots (MOCK FOR NOW until backend route is ready)
    fetchSpots();
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
            } else if (data.type === 'log_event') {
                appendLog(data.log);
            }
        };
    } catch (e) {
        console.log("SSE Init Error", e);
    }
}

async function resolveSpot(spotId) {
    const token = localStorage.getItem('parkme_token');
    try {
        const res = await fetch(`${API_BASE}/sensors/resolve`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ spot_id: spotId })
        });
        
        if (res.ok) {
            showToast(`Spot ${spotId} resolved successfully.`, 'info');
        } else {
            showToast('Simulated: Acknowledge & Resolve clicked!', 'info');
            // Remove the card for demo purposes
            document.getElementById(`spot-${spotId}`)?.remove();
        }
    } catch (e) {
        showToast('Simulated: Spot Acknowledged', 'info');
        document.getElementById(`spot-${spotId}`)?.remove();
    }
}

// Rendering Logic
function createSpotCard(spot) {
    const div = document.createElement('div');
    
    let statusClass = 'free';
    let plateDisplay = 'EMPTY';
    
    if (spot.is_occupied) {
        if (spot.is_violation && spot.license_plate === 'UNIDENTIFIED') {
            statusClass = 'unidentified';
            plateDisplay = '⚠️ UNIDENTIFIED';
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

    const payload = parseJwt(localStorage.getItem('parkme_token'));
    if (payload && payload.role === 'admin') {
        let batt = spot.battery_level !== undefined && spot.battery_level !== null ? `${spot.battery_level}%` : 'N/A';
        let seen = spot.last_seen ? new Date(spot.last_seen).toLocaleTimeString() : 'N/A';
        html += `
            <div style="font-size: 0.8rem; color: #888; margin-top: 10px; border-top: 1px solid #333; padding-top: 5px;">
                <div>🔋 Battery: ${batt}</div>
                <div>📡 Ping: ${seen}</div>
            </div>
        `;
        if (statusClass === 'unidentified') {
            html += `<button class="resolve-btn" onclick="resolveSpot('${spot.id}')" style="margin-top:10px;">Acknowledge & Resolve</button>`;
        }
    }

    div.innerHTML = html;
    return div;
}

function updateSpotUI(spot) {
    const existing = document.getElementById(`spot-${spot.id}`);
    
    // Check role to enforce strict UI view for drivers
    let token = localStorage.getItem('parkme_token');
    let isAdmin = false;
    if (token) {
        try {
            const payload = parseJwt(token);
            isAdmin = payload.role === 'admin';
        } catch (e) {}
    }

    const newCard = createSpotCard(spot);
    if (existing) {
        existing.replaceWith(newCard);
    } else {
        spotsGrid.appendChild(newCard);
    }
}

function appendLog(log) {
    const li = document.createElement('li');
    li.className = 'log-item';
    
    const time = new Date(log.timestamp).toLocaleTimeString();
    let msgClass = '';
    
    if (log.type === 'violation') msgClass = 'violation';
    if (log.type === 'unidentified') msgClass = 'unidentified';

    li.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message ${msgClass}">${log.message}</span>
    `;
    securityLogs.prepend(li);
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
        
        spotsGrid.innerHTML = '';
        data.spots.forEach(updateSpotUI);
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
if (localStorage.getItem('parkme_token')) {
    initDashboard();
}
