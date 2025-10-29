const components = document.querySelectorAll('.component');
const nextBtn = document.getElementById('nextBtn');
const currentComponentSpan = document.getElementById('currentComponent');
const totalComponentsSpan = document.getElementById('totalComponents');
const progressBarFill = document.querySelector('.progress-bar-fill');
const finishedMessage = document.querySelector('.finished-message');

let currentIndex = 0;
totalComponentsSpan.textContent = components.length;

function showComponent(index) {
    components.forEach((component, i) => {
        if (i === index) {
            component.classList.add('active');
        } else {
            component.classList.remove('active');
        }
    });
    currentComponentSpan.textContent = index + 1;
    progressBarFill.style.width = `${((index + 1) / components.length) * 100}%`;
}

function nextComponent() {
    if (currentIndex < components.length - 1) {
        currentIndex++;
        showComponent(currentIndex);
        nextBtn.style.display = 'none';
        setTimeout(() => {
            nextBtn.style.display = 'block';
        }, 5000); // Show "Next" button after 5 seconds
    } else {
        finishTour();
    }
}

function finishTour() {
    components.forEach(component => component.style.display = 'none');
    nextBtn.style.display = 'none';
    document.querySelector('.progress').style.display = 'none';
    document.querySelector('.progress-bar').style.display = 'none';
    finishedMessage.style.display = 'block';
}

function restartTour() {
    currentIndex = 0;
    showComponent(currentIndex);
    finishedMessage.style.display = 'none';
    document.querySelector('.progress').style.display = 'block';
    document.querySelector('.progress-bar').style.display = 'block';
    nextBtn.style.display = 'block';
}

nextBtn.addEventListener('click', nextComponent);

// Auto-progress for the first time
setTimeout(() => {
    nextBtn.style.display = 'block';
}, 5000);

showComponent(currentIndex);