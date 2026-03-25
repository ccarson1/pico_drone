
const socket = new WebSocket("ws://localhost:8000/controls");
let previousAction = "None";

socket.onopen = () => {
    addLog("Connected to control server");
    console.log("Connected to control server");
};

socket.onclose = () => {
    addLog("Disconnected from control server");
    console.log("Disconnected from control server");
};

function sendMessage(msg) {
    if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(msg));
    }
}

const Input = {
    keys: {},

    init() {

        const controlKeys = [
            "w", "a", "s", "d",
            "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
            "Shift", " "
        ];

        document.addEventListener("keydown", e => {

            if (!controlKeys.includes(e.key)) return;

            if (!this.keys[e.key]) {
                sendMessage({
                    key: e.key,
                    state: "down"
                });
            }

            this.keys[e.key] = true;
        });

        document.addEventListener("keyup", e => {

            if (!controlKeys.includes(e.key)) return;

            sendMessage({
                    key: e.key,
                    state: "up"
                });

            this.keys[e.key] = false;
        });
    },

    isDown(key) {
        return this.keys[key];
    }
};

Input.init();

function update() {

    let action = "None";
    

    if (Input.isDown("w")) action = "Move forward";
    if (Input.isDown("s")) action = "Move backward";
    if (Input.isDown("a")) action = "Move left";
    if (Input.isDown("d")) action = "Move right";

    if (Input.isDown(" ")) action = "Move up";
    if (Input.isDown("Shift")) action = "Move down";

    if (Input.isDown("ArrowUp")) action = "Tilt down";
    if (Input.isDown("ArrowDown")) action = "Tilt up";
    if (Input.isDown("ArrowLeft")) action = "Tilt left";
    if (Input.isDown("ArrowRight")) action = "Tilt right";

    
    if (action !== "None" && action !== previousAction) {
         addLog("Current action: " + action);
    }
    previousAction = action;
    requestAnimationFrame(update);
}

let lastSent = -1;

function captureMouseWheel() {
    let wheelValue = 0;
    let lastSent = wheelValue;

    window.addEventListener("wheel", e => {

        wheelValue -= Math.sign(e.deltaY);
        wheelValue = Math.max(0, Math.min(100, wheelValue));

        if (wheelValue !== lastSent) {

            socket.send(JSON.stringify({
                type: "wheel",
                value: wheelValue
            }));

            lastSent = wheelValue;
        }

        document.getElementById("accel").value = wheelValue;
        document.getElementById("accel-val").textContent = wheelValue;

    });
}
captureMouseWheel();

update();
