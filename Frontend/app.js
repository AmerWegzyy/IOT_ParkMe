// Change 'YOUR_CLOUD_RUN_URL' to your actual Cloud Run URL once deployed
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = isLocalhost 
    ? 'http://localhost:8000/api/v1' 
    : 'https://YOUR_CLOUD_RUN_URL/api/v1';

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
        if (typeof firebase === 'undefined' || !firebase.auth) {
            throw new Error('Firebase Auth SDK not loaded. If running locally, make sure you configure your Firebase credentials.');
        }

        // Authenticate directly with Firebase Auth
        const userCredential = await firebase.auth().signInWithEmailAndPassword(email, password);
        const token = await userCredential.user.getIdToken();
        
        localStorage.setItem('parkme_token', token);
        loginError.classList.add('hidden');
        initDashboard();
    } catch (error) {
        loginError.classList.remove('hidden');
        loginError.textContent = error.message;
    }
});

logoutBtn.addEventListener('click', () => {
    if (typeof firebase !== 'undefined' && firebase.auth) {
        firebase.auth().signOut().catch(console.error);
    }
    localStorage.removeItem('parkme_token');
    if (eventSource) eventSource.close();
    dashboardScreen.classList.add('hidden');
    loginScreen.classList.remove('hidden');
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
        window.currentUserProfile = profile;

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
        } else {
            adminPanel.classList.add('hidden');
            dashboardLayout.classList.remove('has-admin');
        }

        // Connect SSE
        connectSSE(token);
        
        // Fetch spots
        fetchSpots();
    } catch (e) {
        console.error("Dashboard initialization failed:", e);
        // Clean up token and show login screen if authentication fails
        localStorage.removeItem('parkme_token');
        loginScreen.classList.remove('hidden');
        dashboardScreen.classList.add('hidden');
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
            } else if (data.type === 'log_event') {
                appendLog(data.log);
            } else if (data.type === 'refresh_logs') {
                fetchLogs();
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

    if (window.currentUserProfile && window.currentUserProfile.role === 'admin') {
        let batt = spot.battery_level !== undefined && spot.battery_level !== null ? `${spot.battery_level}%` : 'N/A';
        let seen = spot.last_seen ? new Date(spot.last_seen).toLocaleTimeString('en-US', { timeZone: 'Asia/Jerusalem' }) : 'N/A';
        html += `
            <div style="font-size: 0.8rem; color: #888; margin-top: 10px; border-top: 1px solid #333; padding-top: 5px;">
                <div>🔋 Battery: ${batt}</div>
                <div>📡 Ping: ${seen}</div>
            </div>
        `;
        if (statusClass === 'unidentified') {
            const lastSeenTime = spot.last_seen ? new Date(spot.last_seen).getTime() : 0;
            const elapsed = Date.now() - lastSeenTime;
            const cooldown = 45000; // 45 seconds

            if (elapsed < cooldown) {
                const remaining = Math.ceil((cooldown - elapsed) / 1000);
                html += `<button id="resolve-btn-${spot.id}" class="resolve-btn" disabled style="margin-top:10px; opacity:0.5; cursor:not-allowed;">Camera Retrying... (${remaining}s)</button>`;
                
                // Start a countdown to enable the button
                setTimeout(() => {
                    const btn = document.getElementById(`resolve-btn-${spot.id}`);
                    if (btn) {
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.style.cursor = 'pointer';
                        btn.innerText = 'Acknowledge & Resolve';
                        btn.setAttribute('onclick', `resolveSpot('${spot.id}')`);
                    }
                }, cooldown - elapsed);

                // Update the countdown text every second
                const interval = setInterval(() => {
                    const btn = document.getElementById(`resolve-btn-${spot.id}`);
                    if (!btn || btn.disabled === false) {
                        clearInterval(interval);
                        return;
                    }
                    const newElapsed = Date.now() - lastSeenTime;
                    const newRemaining = Math.ceil((cooldown - newElapsed) / 1000);
                    if (newRemaining > 0) {
                        btn.innerText = `Camera Retrying... (${newRemaining}s)`;
                    }
                }, 1000);
            } else {
                html += `<button id="resolve-btn-${spot.id}" class="resolve-btn" onclick="resolveSpot('${spot.id}')" style="margin-top:10px;">Acknowledge & Resolve</button>`;
            }
        }
    }

    div.innerHTML = html;
    return div;
}

function updateSpotUI(spot) {
    const existing = document.getElementById(`spot-${spot.id}`);
    
    // Check role to enforce strict UI view for drivers
    let isAdmin = window.currentUserProfile && window.currentUserProfile.role === 'admin';

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
    
    const time = new Date(log.timestamp).toLocaleTimeString('en-US', { timeZone: 'Asia/Jerusalem' });
    let msgClass = '';
    
    if (log.type === 'violation') msgClass = 'violation';
    if (log.type === 'unidentified') msgClass = 'unidentified';

    li.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message ${msgClass}">${log.message}</span>
        ${log.image_data ? `<button class="btn-secondary btn-small" onclick="openImageModal('${log.image_data}')">View Photo</button>` : ''}
    `;
    securityLogs.prepend(li);
}

function openImageModal(url) {
    const modal = document.getElementById('image-modal');
    const img = document.getElementById('modal-image');
    if (modal && img) {
        img.src = url;
        modal.classList.remove('hidden');
    }
}

function closeImageModal() {
    const modal = document.getElementById('image-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.getElementById('modal-image').src = '';
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
const savedToken = localStorage.getItem('parkme_token');
if (savedToken) {
    const payload = parseJwt(savedToken);
    if (payload && payload.exp && payload.exp * 1000 > Date.now()) {
        initDashboard();
    } else {
        localStorage.removeItem('parkme_token');
    }
}
