const compassFace = document.getElementById('compassFace');
const headingText = document.getElementById('heading');

const compassSize = 200;
const compassRadius = compassSize / 2 - 20;

// Radius for direction letters (closer to center)
const letterRadius = compassRadius - 30;

let heading = 0;           // starting heading
let lastTime = Date.now(); // timestamp of last update

// Add directions with proper orientation
const directions = ["N","NE","E","SE","S","SW","W","NW"];
directions.forEach((dir, i) => {
    const angle = i * 45; // degrees around compass
    const rad = (angle - 90) * Math.PI / 180;

    const x = compassSize / 2 + letterRadius * Math.cos(rad);
    const y = compassSize / 2 + letterRadius * Math.sin(rad);

    const el = document.createElement('div');
    el.className = 'direction';
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.textContent = dir;

    // Rotate letters so top points outward, bottom points to center
    el.style.transform = `translate(-50%, -50%) rotate(${angle}deg)`;
    compassFace.appendChild(el);
});

// Add degree marks
for(let i = 0; i < 360; i += 10){
    const mark = document.createElement('div');
    mark.className = 'degree-mark';
    const length = (i % 30 === 0)? 11 : 8;
    mark.style.height = `${length}px`;

    const rad = (i-90) * Math.PI / 180;
    const x = compassSize / 2 + (compassRadius - length) * Math.cos(rad);
    const y = compassSize / 2 + (compassRadius - length) * Math.sin(rad);

    mark.style.left = `${x}px`;
    mark.style.top = `${y-10}px`;
    mark.style.transform = `rotate(${i}deg) translate(-50%, -100%)`;

    compassFace.appendChild(mark);
}

// Update compass face rotation
function updateCompass(heading){
    compassFace.style.transform = `rotate(${-heading}deg)`;
    headingText.textContent = `Heading: ${Math.round((heading + 360) % 360)}°`;
}


function updateHeadingFromGyro(gz) {
    const now = Date.now();
    const dt = (now - lastTime) / 1000; // seconds
    lastTime = now;

    // gz is in °/s
    heading += gz * dt;

    // No modulo: allow continuous rotation
    // heading = (heading + 360) % 360;

    updateCompass(heading);
}


setInterval(()=>{
    const gz = parseFloat(document.getElementById('gz').textContent);
    updateHeadingFromGyro(gz);
}, 100);