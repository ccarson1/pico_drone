let ws = null;

let gauge_0 = document.getElementsByClassName('bar')[0];
let gauge_1 = document.getElementsByClassName('bar')[1];
let gauge_2 = document.getElementsByClassName('bar')[2];
let gauge_3 = document.getElementsByClassName('bar')[3];



let pitch = 0;
let roll = 0;




function updateHorizon(pitch, roll) {
    const horizon = document.getElementById("horizon");
    // Translate vertically for pitch, rotate for roll
    horizon.style.transform = `rotate(${roll}deg) translateY(${pitch}px)`;
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
        document.getElementById("battery").textContent = data.battery + "%";
        //console.log("Received data:", data);

        pitch = data.gyro.x.toFixed(3);
        roll = data.gyro.y.toFixed(3);
        yaw = data.gyro.z.toFixed(3);

        // Motor values
        const motors = data.motors;
        console.log("Motors:", motors);

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
        let tiltText = "Level / flat ✓";
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
let droneConnected = false;

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
        }

    } catch (err) {

        console.error(err);

        document.getElementById("connectStatus").textContent =
            "Connection error";

        btn.disabled = false;
    }

});



// Demo: oscillate pitch and roll

// setInterval(() => {
    
// }, 60);
