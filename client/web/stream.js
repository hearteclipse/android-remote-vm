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

// DataChannel for control (touch, keyboard, etc.)
let controlChannel = null;

// Setup WebRTC connection
async function setupWebRTC() {
    try {
        // Create peer connection with STUN and TURN servers for NAT traversal
        peerConnection = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                {
                    urls: 'turn:34.42.79.210:3478',
                    username: 'user',
                    credential: 'pass'
                },
                {
                    urls: 'turn:openrelay.metered.ca:80',
                    username: 'openrelayproject',
                    credential: 'openrelayproject'
                }
            ]
        });

        // Create DataChannel for control (must be created before offer)
        controlChannel = peerConnection.createDataChannel('control');

        controlChannel.onopen = () => {
            console.log('📡 Control channel opened');
            // Enable touch input on video element
            setupTouchInput();
        };

        controlChannel.onclose = () => {
            console.log('📡 Control channel closed');
        };

        controlChannel.onerror = (error) => {
            console.error('📡 Control channel error:', error);
        };

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
            if (event.candidate) {
                console.log('🧊 ICE candidate:', event.candidate.type, event.candidate.candidate);
                if (websocket.readyState === WebSocket.OPEN) {
                    const candidateMsg = {
                        type: 'ice-candidate',
                        candidate: {
                            candidate: event.candidate.candidate,
                            sdpMid: event.candidate.sdpMid,
                            sdpMLineIndex: event.candidate.sdpMLineIndex,
                            usernameFragment: event.candidate.usernameFragment
                        }
                    };
                    console.log('📤 Sending ICE candidate:', candidateMsg);
                    websocket.send(JSON.stringify(candidateMsg));
                }
            } else {
                console.log('🧊 ICE gathering complete');
            }
        };

        // Monitor connection state
        peerConnection.onconnectionstatechange = () => {
            console.log('🔌 Connection state:', peerConnection.connectionState);
            if (peerConnection.connectionState === 'connected') {
                console.log('✅ WebRTC connection established!');
                updateStatus('connected', 'Connected');
                setLoading(false);
            } else if (peerConnection.connectionState === 'failed') {
                console.error('❌ WebRTC connection failed');
                updateStatus('disconnected', 'Connection failed');
                setLoading(false);
            }
        };

        // Monitor ICE connection state
        peerConnection.oniceconnectionstatechange = () => {
            console.log('🧊 ICE connection state:', peerConnection.iceConnectionState);
            if (peerConnection.iceConnectionState === 'failed' ||
                peerConnection.iceConnectionState === 'disconnected') {
                console.error('❌ ICE connection failed/disconnected');
            }
        };

        // Create and send offer
        const offer = await peerConnection.createOffer({
            offerToReceiveVideo: true,
            offerToReceiveAudio: false
        });

        await peerConnection.setLocalDescription(offer);

        // Optimize SDP for low-latency H.264
        let optimizedSdp = peerConnection.localDescription.sdp;

        // Prefer H.264 baseline profile for low latency
        optimizedSdp = optimizedSdp.replace(
            /a=fmtp:(\d+).*profile-level-id=[0-9a-fA-F]+.*/g,
            'a=fmtp:$1 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f'
        );

        // Remove RTX (retransmission) for lower latency
        optimizedSdp = optimizedSdp.replace(/a=rtpmap:\d+ rtx\/\d+\r\n/g, '');
        optimizedSdp = optimizedSdp.replace(/a=fmtp:\d+ apt=\d+\r\n/g, '');

        console.log('📝 Optimized SDP for low-latency H.264');

        // Send offer through WebSocket (guard against CLOSED/CLOSING)
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({
                type: 'offer',
                sdp: optimizedSdp
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

    // Try DataChannel first (preferred)
    if (controlChannel && controlChannel.readyState === 'open') {
        controlChannel.send(JSON.stringify({
            type: 'keyevent',
            keycode: keyMap[keyName]
        }));
        return;
    }

    // Fallback to WebSocket
    sendInput({
        inputType: 'key',
        keyCode: keyMap[keyName]
    });
}

// Setup touch input on video element
function setupTouchInput() {
    const remoteVideo = document.getElementById('remoteVideo');

    // Remove old listeners
    const newVideo = remoteVideo.cloneNode(true);
    remoteVideo.parentNode.replaceChild(newVideo, remoteVideo);
    const video = document.getElementById('remoteVideo');

    // Handle click/tap
    video.addEventListener('click', (e) => {
        if (!controlChannel || controlChannel.readyState !== 'open') {
            console.warn('Control channel not open');
            return;
        }

        const rect = video.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;

        console.log(`👆 Tap at normalized (${x.toFixed(2)}, ${y.toFixed(2)})`);

        controlChannel.send(JSON.stringify({
            type: 'tap',
            x: x,
            y: y
        }));
    });

    // Handle touch events for mobile
    let touchStartPos = null;

    video.addEventListener('touchstart', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        const rect = video.getBoundingClientRect();
        touchStartPos = {
            x: (touch.clientX - rect.left) / rect.width,
            y: (touch.clientY - rect.top) / rect.height,
            time: Date.now()
        };
    });

    video.addEventListener('touchend', (e) => {
        e.preventDefault();
        if (!controlChannel || controlChannel.readyState !== 'open' || !touchStartPos) {
            return;
        }

        const touch = e.changedTouches[0];
        const rect = video.getBoundingClientRect();
        const endPos = {
            x: (touch.clientX - rect.left) / rect.width,
            y: (touch.clientY - rect.top) / rect.height
        };

        const duration = Date.now() - touchStartPos.time;
        const distance = Math.sqrt(
            Math.pow(endPos.x - touchStartPos.x, 2) +
            Math.pow(endPos.y - touchStartPos.y, 2)
        );

        // If it's a short tap (not a swipe)
        if (distance < 0.05 && duration < 300) {
            console.log(`👆 Tap at normalized (${touchStartPos.x.toFixed(2)}, ${touchStartPos.y.toFixed(2)})`);
            controlChannel.send(JSON.stringify({
                type: 'tap',
                x: touchStartPos.x,
                y: touchStartPos.y
            }));
        } else {
            // It's a swipe
            console.log(`👉 Swipe from (${touchStartPos.x.toFixed(2)}, ${touchStartPos.y.toFixed(2)}) to (${endPos.x.toFixed(2)}, ${endPos.y.toFixed(2)})`);
            controlChannel.send(JSON.stringify({
                type: 'swipe',
                x1: touchStartPos.x,
                y1: touchStartPos.y,
                x2: endPos.x,
                y2: endPos.y,
                duration: Math.min(duration, 500)
            }));
        }

        touchStartPos = null;
    });

    console.log('✅ Touch input enabled');
}

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

    if (controlChannel) {
        controlChannel = null;
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

