document.addEventListener('DOMContentLoaded', function () {
    // Cache DOM elements for wallet interaction
    const walletDropdownToggle = document.getElementById('register-nft-wallet-dropdown-toggle'); // Toggle for the wallet dropdown
    const walletOptions = document.querySelector('.wallet-options'); // Container for wallet options
    const closeWalletOptions = document.querySelector('.close-wallet-options'); // Button to close wallet options
    const walletOptionButtons = document.querySelectorAll('.wallet-option'); // Buttons for selecting a wallet
    const loadingIndicator = document.getElementById('loading-indicator'); // Loading spinner for wallet connection
    const walletViewContainer = document.getElementById('wallet-view-container'); // Container to dynamically load the wallet view

    /**
     * Show wallet options by calling the global show function
     */
    function showWalletOptions() {
        showWalletOptionsGlobal(); // Uses global function to display wallet options
    }

    /**
     * Hide wallet options by calling the global hide function
     */
    function hideWalletOptions() {
        hideWalletOptionsGlobal(); // Uses global function to hide wallet options
    }

    async function connectWallet(walletName) {
        try {
            await connectWalletAndSignMessage(walletName);
            hideWalletOptions();
        } catch (error) {
            handleError(error, 'Failed to connect wallet. Please try again.');
        }
    }

    // Add event listener to the wallet dropdown toggle button
    walletDropdownToggle.addEventListener('click', function (event) {
        event.stopPropagation(); // Prevent event from propagating to parent elements
        const walletOptionsVisible = walletOptions.style.display === 'block'; // Check if wallet options are visible
        if (!walletOptionsVisible) {
            showWalletOptions(); // Show wallet options if they are not visible
        } else {
            hideWalletOptions(); // Hide wallet options if they are visible
        }
    });

    // Add event listeners to wallet option buttons
    walletOptionButtons.forEach(function (button) {
        button.addEventListener('click', async function (event) {
            event.preventDefault(); // Prevent default button action
            const walletName = this.getAttribute('data-wallet'); // Get wallet name from data attribute
            loadingIndicator.style.display = 'block'; // Show loading indicator

            try {
                await connectWallet(walletName); // Attempt to connect to the selected wallet
                hideWalletOptions(); // Hide wallet options after connection
            } catch (error) {
                handleError(error, 'Failed to connect wallet. Please try again.'); // Handle connection errors
            } finally {
                loadingIndicator.style.display = 'none'; // Hide loading indicator
            }
        });
    });

    // Handle clicks outside of wallet options to hide them
    document.addEventListener('click', function (event) {
        const clickedInsideWalletOptions = walletOptions.contains(event.target); // Check if click was inside wallet options
        const clickedInsideWalletDropdownToggle = walletDropdownToggle.contains(event.target); // Check if click was on the dropdown toggle

        if (!clickedInsideWalletOptions && !clickedInsideWalletDropdownToggle) {
            hideWalletOptions(); // Hide wallet options if click was outside
        }
    });

    // Event listener to hide wallet options when close button is clicked
    closeWalletOptions.addEventListener('click', () => {
        walletOptions.style.display = 'none';
    });
});
