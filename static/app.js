let ws = null;

let gauge_0 = document.getElementsByClassName('bar')[0];
let gauge_1 = document.getElementsByClassName('bar')[1];
let gauge_2 = document.getElementsByClassName('bar')[2];
let gauge_3 = document.getElementsByClassName('bar')[3];

let calibrateBtn = document.getElementById("calibrateBtn");



let pitch = 0;
let roll = 0;

let droneConnected = false;


// Example function to add logs
function addLog(message) {
    const container = document.getElementById('logContainer');
    const logLine = document.createElement('div');
    logLine.textContent = message;

    container.appendChild(logLine);

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function updateHorizon(pitchDeg, rollDeg) {
    const horizon = document.getElementById("horizon");
    horizon.style.transform = `rotate(${rollDeg}deg)`;

    const lines = document.querySelectorAll("#pitch-lines .pitch-line");
    const scale = 2; // pixels per degree

    lines.forEach(line => {
        const deg = parseInt(line.dataset.deg);
        line.style.transform = `translateY(${(deg - pitchDeg) * scale}px) translateX(-50%)`;
    });
}

function connectWebSocket() {
    ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => {
        console.log("WebSocket connected");
        document.getElementById("connectStatus").textContent =
            "WebSocket connected — waiting for drone data";
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        document.getElementById("timestamp").textContent = data.timestamp;

        document.getElementById("ax").textContent = data.accel.x.toFixed(3);
        document.getElementById("ay").textContent = data.accel.y.toFixed(3);
        document.getElementById("az").textContent = data.accel.z.toFixed(3);

        document.getElementById("gx").textContent = data.gyro.x.toFixed(3);
        document.getElementById("gy").textContent = data.gyro.y.toFixed(3);
        document.getElementById("gz").textContent = data.gyro.z.toFixed(3);
        document.getElementById("heading").textContent = data.heading.toFixed(1) + "°";
        document.getElementById("battery").textContent = data.battery + "%";
        document.getElementById("altimeter-value").textContent = data.distance + " mm";
        addLog(data.log);
        //console.log("Received data:", data);

        updateAltimeter(data.distance - 75);
        updateCompass(data.heading.toFixed(1));

        pitch = data.gyro.x.toFixed(3);
        roll = data.gyro.y.toFixed(3);
        yaw = data.gyro.z.toFixed(3);

        // Motor values
        const motors = data.motors;
        //console.log("Motors:", motors);

        // Example: update a div in HTML
        document.getElementById("speed-value-0").innerText = motors.motor1;
        document.getElementById("speed-value-1").innerText = motors.motor2;
        document.getElementById("speed-value-2").innerText = motors.motor3;
        document.getElementById("speed-value-3").innerText = motors.motor4;

        gauge_0.style.transform = "rotate(" + String(((motors.motor1 * 1.8) - 90)) + "deg)";
        gauge_1.style.transform = "rotate(" + String(((motors.motor2 * 1.8) - 90)) + "deg)";
        gauge_2.style.transform = "rotate(" + String(((motors.motor3 * 1.8) - 90)) + "deg)";
        gauge_3.style.transform = "rotate(" + String(((motors.motor4 * 1.8) - 90)) + "deg)";


        updateHorizon(pitch, roll);



        // Tilt direction logic
        const threshold = 0.25;
        let tiltText = "Level / flat";
        let tiltColor = "#58a6ff";

        const directions = [];

        if (Math.abs(data.accel.y) > threshold) {
            if (data.accel.y > 0) directions.push("Forward");
            else directions.push("Backward");
        }

        if (Math.abs(data.accel.x) > threshold) {
            if (data.accel.x > 0) directions.push("Right");
            else directions.push("Left");
        }

        if (directions.length > 0) {
            tiltText = directions.join(" + ");
            tiltColor = "#ff7b72";
        }

        if (data.accel.z < 0.5) {
            tiltText = "Strong tilt or upside down!";
            tiltColor = "#ff4444";
        }

        const levelEl = document.getElementById("level");
        levelEl.textContent = "Tilt: " + tiltText;
        levelEl.style.color = tiltColor;

        document.getElementById("connectStatus").textContent =
            "Receiving live data from drone";

        document.getElementById("connectBtn").disabled = false;
    };

    ws.onclose = () => {
        document.getElementById("connectStatus").textContent =
            "Connection lost — reconnecting...";
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        document.getElementById("connectStatus").textContent =
            "WebSocket error";
    };
}

// Start WebSocket immediately
connectWebSocket();


// Connect button logic


document.getElementById("connectBtn").addEventListener("click", async () => {

    const btn = document.getElementById("connectBtn");

    try {

        if (!droneConnected) {

            document.getElementById("connectStatus").textContent =
                "Starting connection to drone...";

            btn.disabled = true;

            const response = await fetch("/connect", { method: "POST" });
            const data = await response.json();

            document.getElementById("connectStatus").textContent =
                "Scanning and connecting...";

            btn.textContent = "Disconnect Drone";
            btn.disabled = false;

            droneConnected = true;

            calibrateBtn.disabled = false;


        } else {

            document.getElementById("connectStatus").textContent =
                "Disconnecting...";

            btn.disabled = true;

            const response = await fetch("/disconnect", { method: "POST" });
            const data = await response.json();

            document.getElementById("connectStatus").textContent =
                "Drone disconnected";

            btn.textContent = "Connect to Drone";
            btn.disabled = false;

            droneConnected = false;

            calibrateBtn.disabled = true;
        }

    } catch (err) {

        console.error(err);

        document.getElementById("connectStatus").textContent =
            "Connection error";

        btn.disabled = false;
    }

});

document.getElementById("calibrateBtn").addEventListener("click", calibrate);

function calibrate() {
    fetch("/calibrate", { method: "POST" })
        .then(r => r.json())
        .then(data => {
            console.log(data);

        })
        .catch(err => {
            console.error(err);
            alert("Calibration failed!");
        });
}

const pitchLinesContainer = document.getElementById("pitch-lines");

// Create pitch lines
for (let deg = -30; deg <= 30; deg += 10) {
    if (deg === 0) continue; // skip zero (the aircraft line already covers this)

    const line = document.createElement("div");
    line.className = "pitch-line";
    line.style.top = `50%`; // center as baseline
    line.dataset.deg = deg;

    // label
    const label = document.createElement("div");
    label.className = "pitch-label";
    label.textContent = `${Math.abs(deg)}°`;
    if (deg < 0) label.style.top = "100%"; // label below for negative pitch
    else label.style.top = "-100%";        // label above for positive pitch

    line.appendChild(label);
    pitchLinesContainer.appendChild(line);
}

function updateAltimeter(distanceMm) {
    const needle = document.getElementById("altimeter-needle");
    const valueDisplay = document.getElementById("altimeter-value");

    // Clamp distance for gauge
    const maxDistance = 3000; // adjust to your max altitude
    const clamped = Math.min(distanceMm, maxDistance);

    // Map distance to degrees (0 mm = 0°, maxDistance = 270°)
    const angle = (clamped / maxDistance) * 270;

    needle.style.transform = `translateX(-50%) rotate(${angle-100}deg)`;
    valueDisplay.textContent = `${distanceMm.toFixed(0)} mm`;
}


// Middle column
function showTab(tab) {
    document.getElementById('videoTab').classList.remove('active');
    document.getElementById('logsTab').classList.remove('active');

    if (tab === 'video') {
        document.getElementById('videoTab').classList.add('active');
    } else {
        document.getElementById('logsTab').classList.add('active');
    }
}

function clearLogs() {
    const container = document.getElementById('logContainer');
    container.innerHTML = '';
}

