document.addEventListener('DOMContentLoaded', function() {
    const vrExperienceType = document.getElementById('vrExperienceType');
    const vrQuality = document.getElementById('vrQuality');
    const vrAudio = document.getElementById('vrAudio');
    const vrInteractionMode = document.getElementById('vrInteractionMode');
    const vrPreviewImage = document.getElementById('vrPreviewImage');
    const vrInstructionsList = document.getElementById('vrInstructionsList');
    const vrCompatibilityResult = document.getElementById('vrCompatibilityResult');

    vrExperienceType.addEventListener('change', updateVRPreview);
    vrQuality.addEventListener('change', updateVRPreview);
    vrAudio.addEventListener('change', updateVRPreview);
    vrInteractionMode.addEventListener('change', updateVRPreview);

    function updateVRPreview() {
        // Update preview image based on selected experience
        const experience = vrExperienceType.value;
        vrPreviewImage.src = `vr-preview-${experience}.jpg`;
        
        // Update VR instructions
        updateVRInstructions(experience);
    }

    function updateVRInstructions(experience) {
        const instructions = getVRInstructions(experience);
        vrInstructionsList.innerHTML = '';
        instructions.forEach(instruction => {
            const li = document.createElement('li');
            li.textContent = instruction;
            vrInstructionsList.appendChild(li);
        });
    }

    function getVRInstructions(experience) {
        // Return instructions based on the selected experience
        switch (experience) {
            case 'traitGallery':
                return [
                    "Use the controller to navigate through the trait gallery",
                    "Point and click to select traits for detailed view",
                    "Use the menu button to switch between trait categories"
                ];
            case 'nftShowcase':
                return [
                    "Walk around to explore the NFT showcase",
                    "Use hand gestures to interact with NFTs",
                    "Say 'Info' to get more details about an NFT"
                ];
            // Add more cases for other experiences
            default:
                return ["Instructions not available for this experience"];
        }
    }

    window.launchVR = function() {
        // Implement VR launch logic here
        alert("Launching VR Experience: " + vrExperienceType.value);
        // In a real implementation, this would initiate the VR experience
    }

    window.checkVRCompatibility = function() {
        // Check if VR is supported in the browser
        if ('xr' in navigator) {
            navigator.xr.isSessionSupported('immersive-vr')
                .then((supported) => {
                    if (supported) {
                        vrCompatibilityResult.textContent = "Your device supports VR!";
                        vrCompatibilityResult.style.color = "green";
                    } else {
                        vrCompatibilityResult.textContent = "VR is not supported on your device.";
                        vrCompatibilityResult.style.color = "red";
                    }
                })
                .catch((error) => {
                    vrCompatibilityResult.textContent = "Error checking VR compatibility: " + error;
                    vrCompatibilityResult.style.color = "red";
                });
        } else {
            vrCompatibilityResult.textContent = "WebXR not available in your browser.";
            vrCompatibilityResult.style.color = "red";
        }
    }

    // Initial update
    updateVRPreview();
});