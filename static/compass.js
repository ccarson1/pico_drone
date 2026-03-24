const compassFace = document.getElementById('compassFace');
const headingText = document.getElementById('heading');

const compassSize = 100;
const compassRadius = compassSize / 2 - 5;

// Radius for direction letters (closer to center)
const letterRadius = compassRadius - 12;

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
for(let i = 0; i < 360; i += 8){
    const mark = document.createElement('div');
    mark.className = 'degree-mark';
    const length = (i % 45 === 0)? 15 : 8;
    mark.style.height = `${length}px`;

    const rad = (i-90) * Math.PI / 180;
    const x = compassSize / 2 + (compassRadius - length) * Math.cos(rad);
    const y = compassSize / 2 + (compassRadius - length) * Math.sin(rad);

    mark.style.left = `${x}px`;
    mark.style.top = `${y-8}px`;
    mark.style.transform = `rotate(${i}deg) translate(-50%, -100%)`;

    compassFace.appendChild(mark);
}

let currentRotation = 0;

function updateCompass(targetHeading){
    // Normalize to 0–360
    targetHeading = (targetHeading + 360) % 360;

    // Compute shortest angular difference
    let delta = targetHeading - currentRotation;

    if (delta > 180) delta -= 360;
    if (delta < -180) delta += 360;

    currentRotation += delta;
    console.log(currentRotation)
    compassFace.style.transform = `rotate(${currentRotation}deg)`;

    headingText.textContent = `Heading: ${Math.round(targetHeading)}°`;
}






// setInterval(()=>{
//     const gz = parseFloat(document.getElementById('gz').textContent);
//     heading = parseFloat(document.getElementById('heading').textContent);
//     updateCompass(heading);
// }, 100);






// setInterval(()=>{
//     const gz = parseFloat(document.getElementById('gz').textContent);
//     const headingValue = parseFloat(document.getElementById('headingValue').textContent);
//     updateCompass(headingValue);
// }, 100);