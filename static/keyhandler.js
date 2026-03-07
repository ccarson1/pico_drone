const display = document.getElementById("keyDisplay");

const socket = new WebSocket("ws://localhost:8000/controls");

socket.onopen = () => {
    console.log("Connected to control server");
};

socket.onclose = () => {
    console.log("Disconnected from control server");
};

const Input = {
    keys: {},

    init() {

        document.addEventListener("keydown", e => {

            if (!this.keys[e.key]) {
                socket.send(JSON.stringify({
                    key: e.key,
                    state: "down"
                }));
            }

            this.keys[e.key] = true;
            e.preventDefault();
        });

        document.addEventListener("keyup", e => {

            socket.send(JSON.stringify({
                key: e.key,
                state: "up"
            }));

            this.keys[e.key] = false;
            e.preventDefault();
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

    display.textContent = action;

    requestAnimationFrame(update);
}

update();
