let ws = null;

let gauge_0 = document.getElementsByClassName('bar')[0];
let gauge_1 = document.getElementsByClassName('bar')[1];
let gauge_2 = document.getElementsByClassName('bar')[2];
let gauge_3 = document.getElementsByClassName('bar')[3];

var slider_0 = document.getElementById("myRange_0");
var slider_1 = document.getElementById("myRange_1");
var slider_2 = document.getElementById("myRange_2");
var slider_3 = document.getElementById("myRange_3");

slider_0.oninput = function () {
    document.getElementById('speed-value-0').innerHTML = this.value;
    gauge_0.style.transform = "rotate(" + String(((this.value * 1.8) - 90)) + "deg)";
}
slider_1.oninput = function () {
    document.getElementById('speed-value-1').innerHTML = this.value;
    gauge_1.style.transform = "rotate(" + String(((this.value * 1.8) - 90)) + "deg)";
}
slider_2.oninput = function () {
    document.getElementById('speed-value-2').innerHTML = this.value;
    gauge_2.style.transform = "rotate(" + String(((this.value * 1.8) - 90)) + "deg)";
}
slider_3.oninput = function () {
    document.getElementById('speed-value-3').innerHTML = this.value;
    gauge_3.style.transform = "rotate(" + String(((this.value * 1.8) - 90)) + "deg)";
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
document.getElementById("connectBtn").addEventListener("click", async () => {

    document.getElementById("connectStatus").textContent =
        "Starting connection to drone...";

    document.getElementById("connectBtn").disabled = true;

    try {

        const response = await fetch("/connect", { method: "POST" });
        const data = await response.json();

        if (data.status === "connection_started") {

            document.getElementById("connectStatus").textContent =
                "Scanning and connecting...";

        } else {

            document.getElementById("connectStatus").textContent =
                data.message || "Already connecting";

            document.getElementById("connectBtn").disabled = false;
        }

    } catch (err) {

        console.error(err);

        document.getElementById("connectStatus").textContent =
            "Failed to trigger connection";

        document.getElementById("connectBtn").disabled = false;

    }
});