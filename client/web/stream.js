// WebRTC streaming client for Android device

// Use relative URLs so it works through Nginx proxy
const API_BASE = '/api';
const WS_BASE = `ws://${window.location.host}/api/sessions/ws`;

let peerConnection = null;
let websocket = null;
let sessionToken = null;
let currentDeviceId = null;

// Status indicators
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const loadingOverlay = document.getElementById('loadingOverlay');

// Update connection status
function updateStatus(status, text) {
    statusDot.className = `status-dot ${status}`;
    statusText.textContent = text;
}

// Show/hide loading overlay
function setLoading(isLoading) {
    loadingOverlay.classList.toggle('hidden', !isLoading);
}

// Fetch devices for a user
async function loadDevices(userId) {
    try {
        const response = await fetch(`${API_BASE}/devices/?user_id=${userId}`);
        const devices = await response.json();

        const deviceSelect = document.getElementById('deviceSelect');
        deviceSelect.innerHTML = '<option value="">Select a device...</option>';

        devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.id;
            option.textContent = `${device.device_name} (${device.status})`;
            option.disabled = device.status !== 'running';
            deviceSelect.appendChild(option);
        });

    } catch (error) {
        console.error('Error loading devices:', error);
        alert('Failed to load devices');
    }
}

// Connect to a device
async function connectToDevice() {
    const userId = document.getElementById('userId').value;
    const deviceId = document.getElementById('deviceSelect').value;

    if (!userId || !deviceId) {
        alert('Please select a user and device');
        return;
    }

    setLoading(true);
    updateStatus('connecting', 'Connecting...');

    try {
        // Create a session
        const sessionResponse = await fetch(`${API_BASE}/sessions/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: parseInt(userId),
                device_id: parseInt(deviceId)
            })
        });

        if (!sessionResponse.ok) {
            const error = await sessionResponse.json();
            throw new Error(error.detail || 'Failed to create session');
        }

        const session = await sessionResponse.json();
        sessionToken = session.session_token;
        currentDeviceId = deviceId;

        // Connect via WebSocket
        await connectWebSocket(sessionToken);

    } catch (error) {
        console.error('Error connecting to device:', error);
        alert(`Failed to connect: ${error.message}`);
        updateStatus('disconnected', 'Disconnected');
        setLoading(false);
    }
}

// Connect WebSocket for WebRTC signaling
async function connectWebSocket(token) {
    return new Promise((resolve, reject) => {
        websocket = new WebSocket(`${WS_BASE}/${token}`);

        websocket.onopen = async () => {
            console.log('WebSocket connected');
            await setupWebRTC();
            resolve();
        };

        websocket.onmessage = async (event) => {
            const message = JSON.parse(event.data);
            await handleSignalingMessage(message);
        };

        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateStatus('disconnected', 'Connection error');
            reject(error);
        };

        websocket.onclose = () => {
            console.log('WebSocket closed');
            updateStatus('disconnected', 'Disconnected');
            cleanup();
            setLoading(false);
        };
    });
}

// Setup WebRTC connection
async function setupWebRTC() {
    try {
        // Create peer connection with STUN and TURN servers for NAT traversal
        peerConnection = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                {
                    urls: 'turn:openrelay.metered.ca:80',
                    username: 'openrelayproject',
                    credential: 'openrelayproject'
                }
            ]
        });

        // Handle incoming tracks
        peerConnection.ontrack = (event) => {
            console.log('Received remote track', event);
            console.log('Stream tracks:', event.streams[0].getTracks());

            const remoteVideo = document.getElementById('remoteVideo');
            const stream = event.streams[0];

            remoteVideo.srcObject = stream;

            // Add event listeners to debug
            remoteVideo.onloadedmetadata = () => {
                console.log('Video metadata loaded');
            };

            remoteVideo.oncanplay = () => {
                console.log('Video can play');
            };

            // Force play with timeout (some browsers need this)
            const playPromise = remoteVideo.play();

            if (playPromise !== undefined) {
                playPromise.then(() => {
                    console.log('Video playing successfully');
                    updateStatus('connected', 'Connected');
                    setLoading(false);
                }).catch(err => {
                    console.error('Error playing video:', err);
                    // Try again without user gesture requirement
                    remoteVideo.muted = true;
                    remoteVideo.play().catch(e => console.error('Retry failed:', e));
                    updateStatus('connected', 'Connected');
                    setLoading(false);
                });
            }

            // Timeout fallback - stop loading after 3 seconds
            setTimeout(() => {
                if (remoteVideo.paused) {
                    console.warn('Video still paused after 3s, forcing stop loading');
                }
                setLoading(false);
                updateStatus('connected', 'Connected');
            }, 3000);
        };

        // Handle ICE candidates
        peerConnection.onicecandidate = (event) => {
            if (event.candidate && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({
                    type: 'ice-candidate',
                    candidate: event.candidate
                }));
            }
        };

        // Create and send offer
        const offer = await peerConnection.createOffer({
            offerToReceiveVideo: true,
            offerToReceiveAudio: false
        });

        await peerConnection.setLocalDescription(offer);

        // Send offer through WebSocket (guard against CLOSED/CLOSING)
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({
                type: 'offer',
                sdp: offer.sdp
            }));
        } else {
            console.warn('WebSocket not open. Aborting offer send.');
            updateStatus('disconnected', 'Connection lost');
            setLoading(false);
            return;
        }

    } catch (error) {
        console.error('Error setting up WebRTC:', error);
        updateStatus('disconnected', 'Setup failed');
        setLoading(false);
    }
}

// Handle signaling messages
async function handleSignalingMessage(message) {
    try {
        switch (message.type) {
            case 'answer':
                const answer = new RTCSessionDescription({
                    type: 'answer',
                    sdp: message.sdp
                });
                await peerConnection.setRemoteDescription(answer);
                console.log('Remote description set');
                break;

            case 'ice-candidate':
                if (message.candidate) {
                    await peerConnection.addIceCandidate(new RTCIceCandidate(message.candidate));
                }
                break;

            case 'error':
                console.error('Server error:', message.message);

                // Check if it's WebRTC unavailable error
                if (message.message && message.message.toLowerCase().includes('not available')) {
                    alert(`WebRTC not available on server.\n\nThe backend needs aiortc and av packages installed.\n\nTo fix:\n1. docker exec -it vmi-backend bash\n2. pip install aiortc av\n3. Restart backend`);
                    updateStatus('disconnected', 'WebRTC unavailable');
                } else {
                    alert(`Error: ${message.message}`);
                    updateStatus('disconnected', 'Error');
                }
                setLoading(false);
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    } catch (error) {
        console.error('Error handling signaling message:', error);
    }
}

// Send input events to device
function sendInput(inputData) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            type: 'input',
            ...inputData
        }));
    }
}

// Send key event
function sendKey(keyName) {
    const keyMap = {
        'HOME': 3,
        'BACK': 4,
        'APP_SWITCH': 187,
        'POWER': 26,
        'VOLUME_UP': 24,
        'VOLUME_DOWN': 25
    };

    sendInput({
        inputType: 'key',
        keyCode: keyMap[keyName]
    });
}

// Handle touch events on video
document.getElementById('remoteVideo').addEventListener('click', (event) => {
    const video = event.target;
    const rect = video.getBoundingClientRect();

    const x = Math.floor((event.clientX - rect.left) / rect.width * 1080);
    const y = Math.floor((event.clientY - rect.top) / rect.height * 2340);

    sendInput({
        inputType: 'touch',
        action: 'tap',
        x: x,
        y: y
    });
});

// Disconnect from device
async function disconnect() {
    if (sessionToken) {
        try {
            await fetch(`${API_BASE}/sessions/${currentDeviceId}/end`, {
                method: 'POST'
            });
        } catch (error) {
            console.error('Error ending session:', error);
        }
    }

    cleanup();
}

// Cleanup connections
function cleanup() {
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }

    if (websocket) {
        websocket.close();
        websocket = null;
    }

    sessionToken = null;
    currentDeviceId = null;

    const remoteVideo = document.getElementById('remoteVideo');
    remoteVideo.srcObject = null;

    updateStatus('disconnected', 'Disconnected');
}

// Load devices when user ID changes
document.getElementById('userId').addEventListener('change', (event) => {
    const userId = event.target.value;
    if (userId) {
        loadDevices(userId);
    }
});

// Initial load
const initialUserId = document.getElementById('userId').value;
if (initialUserId) {
    loadDevices(initialUserId);
}

