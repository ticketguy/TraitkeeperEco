// console.log("wallet-connection.js loaded");

// Constants for the application
const CONSTANTS = {
    TRANSITION_TIME: 300,
    POLLING_INTERVAL: 10000
};

// Global state management
let isWalletConnected = false;
let publicKey = null;
let isDisconnecting = false;

// Cached DOM elements for wallet connection UI
const walletConnectionContainer = document.querySelector('.wallet-connection-container');
const walletOptionsElements = document.querySelectorAll('.wallet-options');
const closeWalletOptionsButtons = document.querySelectorAll('.close-wallet-options');
const walletOptionButtons = document.querySelectorAll('.wallet-option');
const loadingIndicators = document.querySelectorAll('#loading-indicator');
const walletBackdrop = document.getElementById('wallet-backdrop');
// Define userProfileMenus in the global scope - Fix: Use correct IDs
const userProfileMenus = document.querySelectorAll('#user-profile-menu-desktop, #user-profile-menu-mobile');
// console.log('Globally cached user-profile-menus:', userProfileMenus.length);

// Utility Functions
function showWalletOptions() {
    // console.log("Showing wallet options");
    walletOptionsElements.forEach(option => {
        option.classList.remove('hidden');
        setTimeout(() => option.classList.add('opacity-100'), 10);
    });

    if (walletBackdrop) {
        walletBackdrop.classList.remove('hidden');
        setTimeout(() => walletBackdrop.classList.add('opacity-100'), 10);
    }

    document.body.style.overflow = 'hidden';
    if (walletConnectionContainer) {
        walletConnectionContainer.style.display = 'none';
    }
}

function hideWalletOptions() {
    // console.log("Hiding wallet options");
    walletOptionsElements.forEach(option => {
        option.classList.remove('opacity-100');
        option.classList.add('opacity-0');
        setTimeout(() => option.classList.add('hidden'), CONSTANTS.TRANSITION_TIME);
    });

    if (walletBackdrop) {
        walletBackdrop.classList.remove('opacity-100');
        walletBackdrop.classList.add('opacity-0');
        setTimeout(() => walletBackdrop.classList.add('hidden'), CONSTANTS.TRANSITION_TIME);
    }

    document.body.style.overflow = '';
    if (walletConnectionContainer) {
        walletConnectionContainer.style.display = 'block';
    }
}

function handleError(error, customMessage) {
    console.error(customMessage || 'An error occurred:', error);
    const errorMessage = customMessage || 'An error occurred. Please try again.';
    const errorDisplay = document.querySelector('#wallet-error-display') || document.querySelector('#login-error-display') || document.querySelector('#signup-error-display');
    if (errorDisplay) {
        errorDisplay.textContent = errorMessage;
        errorDisplay.classList.remove('hidden');
    } else {
        alert(errorMessage);
    }
}

function addTouchAndClickListener(elements, handler) {
    // console.log("Adding touch and click listeners to elements:", elements);
    elements.forEach(element => {
        element.addEventListener('click', handler);
        element.addEventListener('touchend', function (event) {
            event.preventDefault();
            handler.call(this, event);
        });
    });
}

function getCookie(name) {
    // console.log("Getting cookie:", name);
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    // console.log("Cookie value for", name, ":", cookieValue);
    if (!cookieValue) {
        console.warn(`CSRF token not found. Ensure CSRF cookie is set.`);
    }
    return cookieValue;
}

function startPollingWalletState() {
    // console.log("Starting polling wallet state");
    if (isDisconnecting) {
        // console.log('Polling skipped due to disconnection in progress');
        return;
    }

    const pollingInterval = setInterval(async () => {
        // console.log("Polling wallet state, publicKey:", publicKey);
        if (isDisconnecting || !publicKey) {
            // console.log("Clearing polling interval due to disconnection or no publicKey");
            clearInterval(pollingInterval);
            return;
        }
        try {
            const response = await fetch('/wallet/verify-session/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ public_key: publicKey })
            });

            // console.log("Polling response:", response);
            if (!response.ok) {
                throw new Error('Failed to verify connection state');
            }

            const data = await response.json();
            // console.log("Polling data:", data);
            if (data.status === 'success') {
                updateHeaderWalletState(true, data.username, data.profile_picture);
            } else {
                updateHeaderWalletState(false);
                clearInterval(pollingInterval);
            }
        } catch (error) {
            console.error('Polling error:', error);
            updateHeaderWalletState(false);
            clearInterval(pollingInterval);
        }
    }, CONSTANTS.POLLING_INTERVAL);
}

async function detectWallets() {
    // console.log("Detecting wallets");
    try {
        const supportedWallets = [
            { name: 'Phantom', provider: window.phantom?.solana, icon: 'https://phantom.app/favicon.ico', installLink: 'https://phantom.app/' },
            { name: 'Solflare', provider: window.solflare, icon: 'https://solflare.com/favicon.ico', installLink: 'https://solflare.com/' },
            { name: 'Backpack', provider: window.backpack?.solana, icon: 'https://backpack.app/favicon.ico', installLink: 'https://backpack.app/' },
            { name: 'Glow', provider: window.glow?.solana, icon: 'https://glow.app/favicon.ico', installLink: 'https://glow.app/' },
            { name: 'Slope', provider: window.slope, icon: 'https://solana.com/favicon.ico', installLink: 'https://slope.finance/' },
            { name: 'Sollet', provider: window.sollet, icon: 'https://solana.com/favicon.ico', installLink: 'https://www.sollet.io/' }
        ];

        const additionalWallets = [];
        const knownWalletNames = new Set(supportedWallets.map(wallet => wallet.name.toLowerCase()));

        if (window.solana && typeof window.solana === 'object') {
            const provider = window.solana;
            let walletName = provider.isPhantom ? 'Phantom' :
                provider.isSolflare ? 'Solflare' :
                    provider.isBackpack ? 'Backpack' :
                        provider.isGlow ? 'Glow' :
                            provider.isSlope ? 'Slope' :
                                provider.isSollet ? 'Sollet' : 'Unknown Solana Wallet';

            if (!knownWalletNames.has(walletName.toLowerCase())) {
                additionalWallets.push({
                    name: walletName,
                    provider: provider,
                    icon: provider.icon || 'https://solana.com/favicon.ico',
                    installLink: provider.installLink || 'https://solana.com/wallets',
                    blockchain: 'solana'
                });
                knownWalletNames.add(walletName.toLowerCase());
            }
        }

        for (const key in window) {
            if (key !== 'solana' && window[key] && typeof window[key] === 'object') {
                const provider = window[key];
                const isSolanaWallet = provider.isSolana || provider.publicKey || key.toLowerCase().includes('solana');
                if (provider.connect && provider.signMessage && !knownWalletNames.has(key.toLowerCase()) && isSolanaWallet) {
                    additionalWallets.push({
                        name: key.charAt(0).toUpperCase() + key.slice(1),
                        provider: provider,
                        icon: 'https://solana.com/favicon.ico',
                        installLink: 'https://solana.com/wallets',
                        blockchain: 'solana'
                    });
                    knownWalletNames.add(key.toLowerCase());
                }
            }
        }

        const detectedWallets = supportedWallets.map(wallet => ({
            ...wallet,
            isInstalled: !!wallet.provider,
            blockchain: 'solana'
        })).concat(additionalWallets);

        // console.log(`Detected wallets:`, detectedWallets.map(w => `${w.name} (${w.isInstalled ? 'Installed' : 'Not Installed'}, Blockchain: ${w.blockchain})`).join(', '));
        return detectedWallets;
    } catch (error) {
        console.error('Error detecting wallets:', error);
        return [];
    }
}

async function connectWalletAndSignMessage(wallet, isLinking = false) {
    // console.log("Connecting wallet:", wallet.name);
    if (!wallet || !wallet.provider) {
        throw new Error('Invalid wallet provider');
    }

    if (isWalletConnected && !isLinking) {
        // console.log('Wallet already connected');
        return publicKey;
    }

    try {
        showLoadingIndicator();

        // console.log(`Initiating connection to ${wallet.name}`);

        let connectionResponse;
        if (wallet.name === 'Solflare') {
            if (wallet.provider.isConnected) {
                connectionResponse = { publicKey: wallet.provider.publicKey };
            } else {
                await wallet.provider.connect();
                connectionResponse = { publicKey: wallet.provider.publicKey };
            }
        } else {
            connectionResponse = await wallet.provider.connect();
        }

        if (!connectionResponse || !connectionResponse.publicKey) {
            throw new Error('Failed to retrieve public key from wallet');
        }

        publicKey = connectionResponse.publicKey.toString();
        // console.log("Wallet connected, publicKey:", publicKey);

        const messageText = isLinking
            ? `Sign this message to link. Wallet: ${publicKey}`
            : `Sign this message to log in or create an account. Wallet: ${publicKey}`;
        const message = new TextEncoder().encode(messageText);

        let signedMessage;
        try {
            if (wallet.name === 'Solflare') {
                const signatureData = await wallet.provider.signMessage(message);
                if (signatureData instanceof Uint8Array) {
                    signedMessage = Array.from(signatureData);
                } else if (signatureData && signatureData.signature) {
                    signedMessage = Array.from(signatureData.signature);
                } else {
                    throw new Error('Unexpected signature format from Solflare');
                }
                // console.log("Solflare signatureData:", signatureData);
            } else {
                const signatureData = await wallet.provider.signMessage(message, 'utf8');
                if (!signatureData || !signatureData.signature) {
                    throw new Error('Unexpected signature format from wallet');
                }
                signedMessage = Array.from(signatureData.signature);
                // console.log("Non-Solflare signatureData:", signatureData);
            }
        } catch (error) {
            console.error('Error signing message:', error);
            throw new Error('Failed to sign message. Did you cancel the signing prompt?');
        }

        if (!signedMessage || signedMessage.length === 0) {
            throw new Error('Failed to obtain a valid signature from the wallet');
        }
        // console.log("Message signed, signedMessage:", signedMessage);

        const url = isLinking ? '/wallet/link-wallet/' : '/wallet/session/';
        const data = await createSessionOnServer(publicKey, signedMessage, url);

        if (!isLinking) {
            isWalletConnected = true;
            updateHeaderWalletState(true, data.username, data.profile_picture);
            startPollingWalletState();
        } else {
            updateHeaderWalletState(true, data.username, data.profile_picture);
        }

        return publicKey;

    } catch (error) {
        console.error('Wallet connection error:', error);
        handleError(error, `Failed to connect to ${wallet.name}. ${error.message}`);
        throw error;
    } finally {
        try {
            hideLoadingIndicator();
            const walletOptions = document.querySelector('.wallet-options');
            if (walletOptions) {
                walletOptions.classList.remove('loading');
                walletOptions.style.pointerEvents = 'auto';
            }
            if (walletBackdrop) {
                walletBackdrop.style.pointerEvents = 'auto';
            }
            document.body.style.overflow = '';
        } catch (cleanupError) {
            console.error('Error during cleanup in connectWalletAndSignMessage:', cleanupError);
        }
    }
}

async function checkInitialWalletState() {
    // console.log("Checking initial wallet state");
    if (isWalletConnected) {
        return;
    }

    const wallets = await detectWallets();
    for (const wallet of wallets) {
        if (wallet.isInstalled && wallet.provider.isConnected && wallet.blockchain === 'solana') {
            // First, try to get the public key without signing
            try {
                const walletPublicKey = wallet.provider.publicKey?.toString();

                if (walletPublicKey) {
                    // Check if there's an active session with this public key
                    const response = await fetch('/wallet/verify-session/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ public_key: walletPublicKey })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        if (data.status === 'success') {
                            // Valid session exists! Update UI without requesting signature
                            isWalletConnected = true;
                            publicKey = walletPublicKey;
                            updateHeaderWalletState(true, data.username, data.profile_picture);
                            startPollingWalletState();
                            return;
                        }
                    }
                }
            } catch (error) {
                console.log('No active session found, will request signature');
            }

            // No valid session - proceed with normal connect + sign flow
            await connectWalletAndSignMessage(wallet);
            break;
        }
    }
}

async function createSessionOnServer(publicKey, signedMessage, url) {
    // console.log("Creating session on server, publicKey:", publicKey);
    
    // 1. Convert signature to Base64 (needed for Django/REST transport)
    const signatureArray = new Uint8Array(signedMessage);
    const signatureBase64 = btoa(String.fromCharCode.apply(null, signatureArray));

    const csrftoken = getCookie('csrftoken');
    
    // 2. Combine all data into one body for a single server request
    const requestBody = JSON.stringify({
        public_key: publicKey,
        // Send the signature directly with the public key
        signed_message: signatureBase64 
    });
    // console.log("Request body for session creation:", requestBody);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken || ''
            },
            body: requestBody // Send everything at once
        });

        // console.log("Session/Link response status:", response.status);
        if (!response.ok) {
            const errorData = await response.json();
            console.error("Error response from server:", errorData);
            throw new Error(errorData.error || `Server error: ${response.status}`);
        }

        const data = await response.json();
        // console.log("Session/Link data:", data);
        if (data.status !== 'success') {
            throw new Error(data.error || 'Failed to complete session/link action');
        }
        return data;
    } catch (error) {
        console.error('Session/Link process error:', error);
        throw error;
    }
}

async function disconnectWalletGlobal() {
    // console.log("Disconnecting wallet globally");
    try {
        showLoadingIndicator();

        const response = await fetch('/wallet/disconnect/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        if (!response.ok) {
            throw new Error('Failed to disconnect wallet');
        }

        const data = await response.json();
        if (data.status !== 'success') {
            throw new Error('Failed to disconnect wallet');
        }

        isWalletConnected = false;
        publicKey = null;

        // console.log("Wallet disconnected successfully");
        hideWalletOptions();
        updateHeaderWalletState(false);
    } catch (error) {
        console.error('Disconnect wallet error:', error);
        throw error;
    } finally {
        hideLoadingIndicator();
    }
}

async function updateHeaderWalletState(isConnected, username = '', profilePicture = '') {
    // console.log("Updating header wallet state, isConnected:", isConnected);

    const desktopWalletContainer = document.querySelector('.desktop-header .wallet-container');
    const mobileHeaderRight = document.querySelector('.mobile-header .mobile-header-right');

    // console.log('Found desktop-wallet-container:', !!desktopWalletContainer);
    // console.log('Found mobile-header-right:', !!mobileHeaderRight);
    // console.log('Found user-profile-menus:', userProfileMenus.length);

    if (isConnected) {
        // Fetch unread notification count
        let unreadCount = 0;
        try {
            const response = await fetch('/wallet/get-unread-notifications-count/', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success') {
                    unreadCount = data.unread_count;
                    // console.log("Unread notifications count:", unreadCount);
                }
            }
        } catch (error) {
            console.error('Error fetching unread notifications count:', error);
        }

        // Update desktop header
        if (desktopWalletContainer) {
            const desktopToggle = desktopWalletContainer.querySelector('#wallet-dropdown-toggle');
            if (desktopToggle) {
                desktopToggle.classList.add('hidden');
            }

            let userProfile = desktopWalletContainer.querySelector('.user-profile');
            if (!userProfile) {
                const profileHtml = `
                    <div class="user-profile relative flex items-center space-x-2 animate-slide-up">
                        <div class="profile-link flex items-center space-x-2 cursor-pointer">
                            <div id="wallet-profile-image" class="w-8 h-8 rounded-full overflow-hidden border-2 border-primary">
                                <img src="${profilePicture || '/static/img/smileyy.jpg'}" alt="user_pfp" class="w-full h-full object-cover">
                            </div>
                            <div class="flex flex-col">
                                <span class="profile_username font-semibold text-text-light dark:text-text-dark">
                                    ${username ? (username.length > 10 ? username.substring(0, 10) + '...' : username) : 'Anonymous'}
                                </span>
                            </div>
                        </div>
                    </div>
                `;
                const themeToggle = desktopWalletContainer.querySelector('#theme-toggle');
                desktopWalletContainer.insertBefore(new DOMParser().parseFromString(profileHtml, 'text/html').body.firstChild, themeToggle);
            } else {
                const profileImage = userProfile.querySelector('img');
                const profileUsername = userProfile.querySelector('.profile_username');
                if (profileImage && profilePicture) {
                    profileImage.src = profilePicture;
                }
                if (profileUsername && username) {
                    profileUsername.textContent = username.length > 10 ? username.substring(0, 10) + '...' : username;
                }
                userProfile.classList.remove('hidden');
            }

            const notificationToggle = desktopWalletContainer.querySelector('#notification-toggle');
            if (notificationToggle) {
                notificationToggle.classList.remove('hidden');
                // Update the badge with unread count
                let existingBadge = notificationToggle.querySelector('.bg-red-500');
                if (unreadCount > 0) {
                    if (existingBadge) {
                        existingBadge.textContent = unreadCount;
                    } else {
                        const newBadge = document.createElement('span');
                        newBadge.className = 'absolute top-0 right-0 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center animate-pulse';
                        newBadge.textContent = unreadCount;
                        notificationToggle.appendChild(newBadge);
                    }
                } else if (existingBadge) {
                    existingBadge.remove();
                }
            }
        }

        // Update mobile header
        if (mobileHeaderRight) {
            const mobileToggle = mobileHeaderRight.querySelector('#wallet-dropdown-toggle-mobile');
            if (mobileToggle) {
                mobileToggle.classList.add('hidden');
            }

            let userProfile = mobileHeaderRight.querySelector('.user-profile');
            if (!userProfile) {
                const profileHtml = `
                    <div class="user-profile relative flex items-center space-x-2 animate-slide-up">
                        <div class="profile-link flex items-center space-x-2 cursor-pointer">
                            <div id="wallet-profile-image-mobile" class="w-8 h-8 rounded-full overflow-hidden border-2 border-primary">
                                <img src="${profilePicture || '/static/img/smileyy.jpg'}" alt="user_pfp" class="w-full h-full object-cover">
                            </div>
                        </div>
                    </div>
                `;
                const mobileMenuToggle = mobileHeaderRight.querySelector('.mobile-menu-toggle');
                mobileHeaderRight.insertBefore(new DOMParser().parseFromString(profileHtml, 'text/html').body.firstChild, mobileMenuToggle);
            } else {
                const profileImage = userProfile.querySelector('img');
                if (profileImage && profilePicture) {
                    profileImage.src = profilePicture;
                }
                userProfile.classList.remove('hidden');
            }

            const notificationToggle = mobileHeaderRight.querySelector('#notification-toggle-mobile');
            if (notificationToggle) {
                notificationToggle.classList.remove('hidden');
                // Update the badge with unread count
                let existingBadge = notificationToggle.querySelector('.bg-red-500');
                if (unreadCount > 0) {
                    if (existingBadge) {
                        existingBadge.textContent = unreadCount;
                    } else {
                        const newBadge = document.createElement('span');
                        newBadge.className = 'absolute top-0 right-0 bg-red-500 text-white text-[10px] xs:text-xs rounded-full w-4 xs:w-5 h-4 xs:h-5 flex items-center justify-center animate-pulse';
                        newBadge.textContent = unreadCount;
                        notificationToggle.appendChild(newBadge);
                    }
                } else if (existingBadge) {
                    existingBadge.remove();
                }
            }
        }

        // Initialize WebSocket connection for real-time notifications
        initializeNotificationWebSocket();
    } else {
        // Logged-out state
        if (desktopWalletContainer) {
            const userProfile = desktopWalletContainer.querySelector('.user-profile');
            const notificationToggle = desktopWalletContainer.querySelector('#notification-toggle');
            if (userProfile) {
                userProfile.classList.add('hidden');
            }
            if (notificationToggle) {
                notificationToggle.classList.add('hidden');
            }

            let toggle = desktopWalletContainer.querySelector('#wallet-dropdown-toggle');
            if (!toggle) {
                const toggleHtml = `
                    <button id="wallet-dropdown-toggle" class="bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark transition faint-glow-hover">
                        Login/Signup
                    </button>
                `;
                const themeToggle = desktopWalletContainer.querySelector('#theme-toggle');
                desktopWalletContainer.insertBefore(new DOMParser().parseFromString(toggleHtml, 'text/html').body.firstChild, themeToggle);
            } else {
                toggle.classList.remove('hidden');
            }
        }

        if (mobileHeaderRight) {
            const userProfile = mobileHeaderRight.querySelector('.user-profile');
            const notificationToggle = mobileHeaderRight.querySelector('#notification-toggle-mobile');
            if (userProfile) {
                userProfile.classList.add('hidden');
            }
            if (notificationToggle) {
                notificationToggle.classList.add('hidden');
            }

            let toggle = mobileHeaderRight.querySelector('#wallet-dropdown-toggle-mobile');
            if (!toggle) {
                const toggleHtml = `
                    <button id="wallet-dropdown-toggle-mobile" class="bg-primary text-white px-2 xs:px-3 py-1 xs:py-1.5 text-xs xs:text-sm rounded-lg hover:bg-primary-dark transition faint-glow-hover">
                        Login/Signup
                    </button>
                `;
                const mobileMenuToggle = mobileHeaderRight.querySelector('.mobile-menu-toggle');
                mobileHeaderRight.insertBefore(new DOMParser().parseFromString(toggleHtml, 'text/html').body.firstChild, mobileMenuToggle);
            } else {
                toggle.classList.remove('hidden');
            }
        }

        userProfileMenus.forEach(menu => {
            if (menu) {
                menu.style.display = 'none';
            }
        });
    }
}

function updateWalletList(wallets) {
    // console.log("Updating wallet list, wallets:", wallets);
    const walletList = document.getElementById('detected-wallets');
    const loadingIndicator = document.getElementById('loading-indicator');
    const noWalletsMessage = document.getElementById('no-wallets-message');

    if (!walletList || !loadingIndicator || !noWalletsMessage) {
        console.error('Required DOM elements not found');
        return;
    }

    loadingIndicator.style.display = 'block';
    walletList.innerHTML = '';

    function renderWalletOptions(walletsToShow) {
        walletList.innerHTML = walletsToShow.map(wallet => `
            <div class="wallet-option flex items-center p-3 rounded-lg transition-all duration-200 cursor-pointer ${wallet.isInstalled ? 'hover:bg-primary hover:text-white' : 'opacity-50 cursor-not-allowed'}" data-wallet-name="${wallet.name}">
                <img src="${wallet.icon}" alt="${wallet.name} icon" class="w-8 h-8 mr-3 rounded-full">
                <span class="flex-1 text-lg font-medium">${wallet.name}</span>
                ${wallet.isInstalled ?
                '<span class="wallet-status text-sm bg-accent-light dark:bg-accent-dark px-2 py-1 rounded-full">Installed</span>' :
                `<a href="${wallet.installLink}" target="_blank" class="wallet-status text-sm bg-gray-200 dark:bg-gray-600 px-2 py-1 rounded-full hover:bg-gray-300 dark:hover:bg-gray-500">Install</a>`
            }
            </div>
        `).join('');

        const walletOptions = document.querySelectorAll('.wallet-option');
        walletOptions.forEach(option => {
            option.addEventListener('click', async (event) => {
                const walletName = option.getAttribute('data-wallet-name');
                const wallet = wallets.find(w => w.name === walletName);
                const isLinking = window.location.pathname.includes('/wallet/settings/');

                if (wallet && wallet.isInstalled) {
                    try {
                        await connectWalletAndSignMessage(wallet, isLinking);
                        hideWalletOptions();
                    } catch (error) {
                        console.error('Error connecting wallet:', error);
                        handleError(error, `Failed to connect ${walletName}. Please ensure the wallet is installed and try again.`);
                    }
                } else {
                    event.stopPropagation();
                }
            });
        });
    }

    if (wallets.length > 0) {
        renderWalletOptions(wallets);
        noWalletsMessage.style.display = 'none';
    } else {
        noWalletsMessage.style.display = 'block';
    }

    loadingIndicator.style.display = 'none';
}

function showLoadingIndicator() {
    // console.log("Showing loading indicator");
    loadingIndicators.forEach(indicator => {
        indicator.classList.remove('hidden');
        indicator.classList.add('flex');
    });
    const loadingBackdrop = document.querySelector('.loading-backdrop');
    const walletOptions = document.querySelector('.wallet-options');

    if (loadingBackdrop && walletOptions) {
        loadingBackdrop.classList.remove('hidden');
        walletOptions.classList.add('loading');
        walletOptions.style.pointerEvents = 'none';
    }
    if (walletBackdrop) {
        walletBackdrop.style.pointerEvents = 'none';
    }
    document.body.style.overflow = 'hidden';
}

function hideLoadingIndicator() {
    // console.log("Hiding loading indicator");
    loadingIndicators.forEach(indicator => {
        indicator.classList.add('hidden');
        indicator.classList.remove('flex');
    });
    const loadingBackdrop = document.querySelector('.loading-backdrop');
    const walletOptions = document.querySelector('.wallet-options');

    if (loadingBackdrop && walletOptions) {
        loadingBackdrop.classList.add('hidden');
        walletOptions.classList.remove('loading');
        walletOptions.style.pointerEvents = 'auto';
    }
    if (walletBackdrop) {
        walletBackdrop.style.pointerEvents = 'auto';
    }
    document.body.style.overflow = '';
}

// Form Validation for Email and Password
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const passwordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;

function validateEmail(email, errorElement) {
    if (!emailRegex.test(email)) {
        errorElement.textContent = 'Please enter a valid email address.';
        errorElement.classList.remove('hidden');
        return false;
    }
    errorElement.classList.add('hidden');
    return true;
}

function validatePassword(password, errorElement) {
    if (!passwordRegex.test(password)) {
        errorElement.textContent = 'Password must be at least 8 characters long, with 1 uppercase, 1 lowercase, 1 number, and 1 special character.';
        errorElement.classList.remove('hidden');
        return false;
    }
    errorElement.classList.add('hidden');
    return true;
}

// Function to position the dropdown menu
function positionDropdownMenu(associatedMenu, profileLink) {
    const profileRect = profileLink.getBoundingClientRect();
    associatedMenu.style.top = `${profileRect.bottom}px`; // Position below the profile image, relative to viewport
    associatedMenu.style.right = '50px'; // Push both desktop and mobile dropdowns to the right to avoid notification bell
    associatedMenu.style.left = 'auto';
}

// Function to initialize WebSocket connection for notifications
function initializeNotificationWebSocket() {
    // Close any existing WebSocket connection
    if (window.notificationSocket) {
        window.notificationSocket.close();
        window.notificationSocket = null;
    }

    // Establish new WebSocket connection (use wss:// for HTTPS, ws:// for HTTP)
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    window.notificationSocket = new WebSocket(wsProtocol + '//' + window.location.host + '/ws/notifications/');

    window.notificationSocket.onopen = function () {
        // console.log("Notification WebSocket connection established");
    };

    window.notificationSocket.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.type === "notification") {
            const notificationList = document.getElementById('notification-list');
            const notificationListMobile = document.getElementById('notification-list-mobile');
            const badge = document.querySelectorAll('.bg-red-500');
            let count = badge.length > 0 ? parseInt(badge[0].textContent) + 1 : 1;

            const notificationItem = document.createElement('div');
            notificationItem.className = 'notification-item p-2 border-b border-accent-light dark:border-accent-dark bg-accent-light dark:bg-gray-700 animate-scale-in';
            notificationItem.innerHTML = `
                <p class="text-sm text-text-light dark:text-text-dark">${data.message}</p>
                <p class="text-xs text-text-secondary-light dark:text-text-secondary-dark">Just now</p>
            `;
            if (notificationList) {
                notificationList.prepend(notificationItem);
            }
            if (notificationListMobile) {
                notificationListMobile.prepend(notificationItem.cloneNode(true));
            }

            document.querySelectorAll('#notification-toggle, #notification-toggle-mobile').forEach(toggle => {
                let existingBadge = toggle.querySelector('.bg-red-500');
                if (existingBadge) {
                    existingBadge.textContent = count;
                } else {
                    const newBadge = document.createElement('span');
                    newBadge.className = `absolute top-0 right-0 bg-red-500 text-white rounded-full flex items-center justify-center animate-pulse ${toggle.id === 'notification-toggle' ? 'text-xs w-5 h-5' : 'text-[10px] xs:text-xs w-4 xs:w-5 h-4 xs:h-5'
                        }`;
                    newBadge.textContent = count;
                    toggle.appendChild(newBadge);
                }
            });
        }
    };

    window.notificationSocket.onclose = function () {
        // console.log("Notification WebSocket connection closed");
    };

    window.notificationSocket.onerror = function (error) {
        // Silently handle WebSocket errors when server is unavailable
        // console.error("Notification WebSocket error:", error);
    };
}


document.addEventListener('DOMContentLoaded', async () => {
    // console.log("DOMContentLoaded event fired in wallet-connection.js");
    try {
        await new Promise(resolve => setTimeout(resolve, 500));

        const wallets = await detectWallets();
        updateWalletList(wallets);

        if (!isWalletConnected) {
            checkInitialWalletState();
        }

        // Check for Google signup data
        const response = await fetch('/wallet/get-google-signup-data/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();
        if (data.status === 'success' && data.google_data) {
            // console.log("Google signup data found:", data.google_data);
            showWalletOptions(); // Ensure the wallet modal is open
            showGoogleSignupForm(data.google_data);
        }

        // Use event delegation for event listeners to avoid reattachment
        document.addEventListener('click', function (event) {
            const target = event.target;

            // Handle wallet dropdown toggle (Login/Signup button)
            if (target.matches('#wallet-dropdown-toggle, #wallet-dropdown-toggle-mobile')) {
                event.stopPropagation();
                const walletOptionsVisible = Array.from(walletOptionsElements).some(option => !option.classList.contains('hidden'));
                if (!walletOptionsVisible) {
                    showWalletOptions();
                } else {
                    hideWalletOptions();
                }
            }

            // Handle close wallet options
            if (target.matches('.close-wallet-options')) {
                event.stopPropagation();
                hideWalletOptions();
            }

            // Handle disconnect/logout
            if (target.matches('#disconnect-wallet-desktop, #disconnect-wallet-mobile')) {
                event.preventDefault();
                disconnectWalletGlobal().catch(error => {
                    handleError(error, 'Failed to logout. Please try again.');
                });
            }

            // Handle profile link clicks (dropdown toggle)
            if (target.closest('.profile-link')) {
                const profileLink = target.closest('.profile-link');
                const userProfile = profileLink.closest('.user-profile');
                const associatedMenu = userProfile.querySelector('#user-profile-menu, #user-profile-menu-mobile');
                if (associatedMenu) {
                    positionDropdownMenu(associatedMenu, profileLink);
                    const isVisible = associatedMenu.style.display === 'block';
                    associatedMenu.style.display = isVisible ? 'none' : 'block';
                    // console.log(`User profile menu display set to: ${associatedMenu.style.display}`);
                }
            }

            // Close dropdowns when clicking outside
            const clickedInsideWalletOptions = Array.from(walletOptionsElements).some(option => option.contains(target));
            const clickedInsideWalletDropdownToggle = target.matches('#wallet-dropdown-toggle, #wallet-dropdown-toggle-mobile');
            const clickedInsideUserProfileMenu = Array.from(userProfileMenus).some(menu => menu.contains(target));

            const walletOptionsVisible = Array.from(walletOptionsElements).some(option => !option.classList.contains('hidden'));
            const userProfileMenuVisible = Array.from(userProfileMenus).some(menu => menu && menu.style.display !== 'none');

            if (!clickedInsideWalletOptions && !clickedInsideWalletDropdownToggle && !clickedInsideUserProfileMenu) {
                if (walletOptionsVisible) {
                    hideWalletOptions();
                }
                userProfileMenus.forEach(menu => {
                    if (menu && userProfileMenuVisible) {
                        menu.style.display = 'none';
                    }
                });
            }
        });

        // Touch events for mobile (using event delegation)
        let isTouchEvent = false;
        document.addEventListener('touchstart', function (event) {
            const target = event.target;
            if (target.closest('.profile-link')) {
                isTouchEvent = true;
            }
        });

        document.addEventListener('touchend', function (event) {
            const target = event.target;
            if (target.closest('.profile-link')) {
                event.stopPropagation();
                event.preventDefault();
                // console.log('Profile link touched');

                const profileLink = target.closest('.profile-link');
                const userProfile = profileLink.closest('.user-profile');
                const associatedMenu = userProfile.querySelector('#user-profile-menu, #user-profile-menu-mobile');
                if (associatedMenu) {
                    positionDropdownMenu(associatedMenu, profileLink);
                    const isVisible = associatedMenu.style.display === 'block';
                    associatedMenu.style.display = isVisible ? 'none' : 'block';
                    // console.log(`User profile menu display set to: ${associatedMenu.style.display}`);
                }

                setTimeout(() => { isTouchEvent = false; }, 300);
            }
        });

        // Mouse events for desktop (using event delegation)
        document.addEventListener('mouseover', function (event) {
            const target = event.target;
            if (target.closest('.profile-link')) {
                const profileLink = target.closest('.profile-link');
                const userProfile = profileLink.closest('.user-profile');
                const associatedMenu = userProfile.querySelector('#user-profile-menu, #user-profile-menu-mobile');
                if (associatedMenu) {
                    positionDropdownMenu(associatedMenu, profileLink);
                    associatedMenu.style.display = 'block';
                }
            }
        });

        document.addEventListener('mouseout', function (event) {
            const target = event.target;
            if (target.closest('.profile-link')) {
                const profileLink = target.closest('.profile-link');
                const userProfile = profileLink.closest('.user-profile');
                const associatedMenu = userProfile.querySelector('#user-profile-menu, #user-profile-menu-mobile');
                if (associatedMenu) {
                    setTimeout(() => {
                        if (!associatedMenu.matches(':hover')) {
                            associatedMenu.style.display = 'none';
                        }
                    }, 200);
                }
            }
        });

        // Handle window resize to reposition the dropdown if visible
        window.addEventListener('resize', () => {
            userProfileMenus.forEach(menu => {
                if (menu.style.display === 'block') {
                    const profileLink = menu.closest('.user-profile')?.querySelector('.profile-link');
                    if (profileLink) {
                        positionDropdownMenu(menu, profileLink);
                    }
                }
            });
        });


        // email-login-form handler
        const emailLoginForm = document.querySelector('#email-login-form');
        if (emailLoginForm) {
            emailLoginForm.addEventListener('submit', async function (event) {
                event.preventDefault();
                const usernameOrEmail = this.querySelector('input[name="username_or_email"]').value;  // Updated field name
                const password = this.querySelector('input[name="password"]').value;
                const usernameOrEmailError = this.querySelector('#username-or-email-error');  // Updated ID
                const passwordError = this.querySelector('#password-error');
                const loginErrorDisplay = this.querySelector('#login-error-display');

                // Validate inputs
                let isValid = true;
                if (!usernameOrEmail) {
                    usernameOrEmailError.textContent = 'Please enter your username or email.';
                    usernameOrEmailError.classList.remove('hidden');
                    isValid = false;
                } else {
                    usernameOrEmailError.classList.add('hidden');
                }

                const isPasswordValid = validatePassword(password, passwordError);

                if (!isValid || !isPasswordValid) {
                    return;
                }

                try {
                    showLoadingIndicator();

                    const formData = new FormData();
                    formData.append('username_or_email', usernameOrEmail);  // Updated field name
                    formData.append('password', password);
                    formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

                    const response = await fetch('/wallet/email-login/', {
                        method: 'POST',
                        body: formData
                    });

                    if (!response.ok) {
                        const responseText = await response.text();
                        console.error('Failed to login:', response.status, responseText);
                        throw new Error(`Login request failed: ${response.status} ${response.statusText}`);
                    }

                    const data = await response.json();
                    if (data.status === 'success') {
                        // console.log("Email login successful");
                        isWalletConnected = true;
                        updateHeaderWalletState(true, data.username, data.profile_picture);
                        hideWalletOptions();
                    } else {
                        if (loginErrorDisplay) {
                            loginErrorDisplay.textContent = data.error || 'Login failed. Please try again.';
                            loginErrorDisplay.classList.remove('hidden');
                            if (data.error === 'Invalid username/email or password' && !data.exists) {
                                const signupLink = document.createElement('a');
                                signupLink.href = '/wallet/email-signup/';
                                signupLink.textContent = ' Create an account';
                                signupLink.className = 'text-primary hover:underline';
                                signupLink.addEventListener('click', (e) => {
                                    e.preventDefault();
                                    showSignupForm();
                                });
                                loginErrorDisplay.appendChild(signupLink);
                            }
                        } else {
                            handleError(new Error(data.error), data.error || 'Login failed. Please try again.');
                        }
                    }
                } catch (error) {
                    console.error('Email login error:', error);
                    if (loginErrorDisplay) {
                        loginErrorDisplay.textContent = 'An error occurred during login. Please try again.';
                        loginErrorDisplay.classList.remove('hidden');
                    } else {
                        handleError(error, 'An error occurred during login. Please try again.');
                    }
                } finally {
                    hideLoadingIndicator();
                }
            });
        }

        // Add event listener for "Forgot Password?" link
        const forgotPasswordLink = document.querySelector('#forgot-password-link');
        if (forgotPasswordLink) {
            forgotPasswordLink.addEventListener('click', (e) => {
                e.preventDefault();
                showPasswordResetForm();
            });
        }

  
        function showSignupForm() {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const walletTabContent = document.getElementById('wallet-tab-content');
            const loginTabContent = document.getElementById('login-tab-content');

            walletTabContent.classList.add('hidden', 'opacity-0');
            loginTabContent.classList.add('hidden', 'opacity-0');

            const signupForm = document.createElement('div');
            signupForm.id = 'signup-tab-content';
            signupForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            signupForm.innerHTML = `
        <form id="email-signup-form" method="POST">
            <div class="mb-2">
                <label for="signup-username" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1 transition-transform duration-300 transform translate-x-[-20px] opacity-0 animate-slide-in">Username</label>
                <div class="relative">
                    <input type="text" id="signup-username" name="username" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                    <i class="fas fa-user absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
                <p id="signup-username-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
            </div>
            <div class="mb-2">
                <label for="signup-email" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1 transition-transform duration-300 transform translate-x-[-20px] opacity-0 animate-slide-in">Email</label>
                <div class="relative">
                    <input type="email" id="signup-email" name="email" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                    <i class="fas fa-envelope absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
                <p id="signup-email-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
            </div>
            <div class="mb-2">
                <label for="signup-password" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1 transition-transform duration-300 transform translate-x-[-20px] opacity-0 animate-slide-in-delayed">Password</label>
                <div class="relative">
                    <input type="password" id="signup-password" name="password" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                    <i class="fas fa-lock absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
                <p id="signup-password-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
            </div>
            <button type="submit" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto faint-glow-hover">Sign Up</button>
            <p id="signup-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
            <p class="text-center text-xs mt-2">
                Already have an account? <a href="#" class="text-primary hover:underline" id="back-to-login">Log in</a>
            </p>
        </form>
    `;

            tabContentContainer.appendChild(signupForm);

            const emailSignupForm = document.querySelector('#email-signup-form');
            emailSignupForm.addEventListener('submit', async function (event) {
                event.preventDefault();
                const username = this.querySelector('input[name="username"]').value;
                const email = this.querySelector('input[name="email"]').value;
                const password = this.querySelector('input[name="password"]').value;
                const usernameError = this.querySelector('#signup-username-error');
                const emailError = this.querySelector('#signup-email-error');
                const passwordError = this.querySelector('#signup-password-error');
                const signupErrorDisplay = this.querySelector('#signup-error-display');

                // Validate inputs
                let isValid = true;
                if (!username) {
                    usernameError.textContent = 'Please enter a username.';
                    usernameError.classList.remove('hidden');
                    isValid = false;
                } else {
                    usernameError.classList.add('hidden');
                }

                const isEmailValid = validateEmail(email, emailError);
                const isPasswordValid = validatePassword(password, passwordError);

                if (!isValid || !isEmailValid || !isPasswordValid) {
                    return;
                }

                try {
                    showLoadingIndicator();

                    const formData = new FormData();
                    formData.append('username', username);
                    formData.append('email', email);
                    formData.append('password', password);
                    formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

                    const response = await fetch('/wallet/email-signup/', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        // console.log("Email signup successful");
                        isWalletConnected = true;
                        updateHeaderWalletState(true, data.username, data.profile_picture);
                        hideWalletOptions();
                    } else if (data.status === 'verification_required') {
                        // console.log("Verification required, showing code input form");
                        showVerificationForm(data.email, data.email_error);
                    } else {
                        if (signupErrorDisplay) {
                            signupErrorDisplay.textContent = data.error || 'Signup failed. Please try again.';
                            signupErrorDisplay.classList.remove('hidden');
                        } else {
                            handleError(new Error(data.error), data.error || 'Signup failed. Please try again.');
                        }
                    }
                } catch (error) {
                    console.error('Email signup error:', error);
                    if (signupErrorDisplay) {
                        signupErrorDisplay.textContent = 'An error occurred during signup. Please try again.';
                        signupErrorDisplay.classList.remove('hidden');
                    } else {
                        handleError(error, 'An error occurred during signup. Please try again.');
                    }
                } finally {
                    hideLoadingIndicator();
                }
            });

            const backToLoginLink = document.querySelector('#back-to-login');
            backToLoginLink.addEventListener('click', (e) => {
                e.preventDefault();
                signupForm.remove();
                loginTabContent.classList.remove('hidden');
                setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
            });
        }

        function showVerificationForm(email, emailError = null) {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const signupTabContent = document.getElementById('signup-tab-content');

            signupTabContent.classList.add('hidden', 'opacity-0');

            const verificationForm = document.createElement('div');
            verificationForm.id = 'verification-tab-content';
            verificationForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            verificationForm.innerHTML = `
        <div class="text-center">
            <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">A verification code has been sent to <span class="font-bold">${email}</span>. Please enter the code below.</p>
            ${emailError ? `<p class="text-red-500 text-xs mb-2">${emailError}</p>` : ''}
            <div class="mb-2">
                <label for="verification-code" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1">Verification Code</label>
                <div class="relative">
                    <input type="text" id="verification-code" name="code" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                    <i class="fas fa-key absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
                <p id="verification-code-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
            </div>
            <button id="submit-verification-code" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Verify Code</button>
            <p id="verification-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
            <p class="text-center text-xs mt-2">
                Back to <a href="#" class="text-primary hover:underline" id="back-to-signup">Sign Up</a>
            </p>
        </div>
    `;

            tabContentContainer.appendChild(verificationForm);

            const submitVerificationButton = verificationForm.querySelector('#submit-verification-code');
            const codeInput = verificationForm.querySelector('#verification-code');
            const codeError = verificationForm.querySelector('#verification-code-error');
            const verificationErrorDisplay = verificationForm.querySelector('#verification-error-display');

            submitVerificationButton.addEventListener('click', async () => {
                const code = codeInput.value.trim();
                if (!code) {
                    codeError.textContent = 'Please enter the verification code.';
                    codeError.classList.remove('hidden');
                    return;
                }

                try {
                    showLoadingIndicator();

                    const formData = new FormData();
                    formData.append('code', code);
                    formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

                    const response = await fetch('/wallet/verify-email-code/', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        // console.log("Email verification successful");
                        isWalletConnected = true;
                        updateHeaderWalletState(true, data.username, data.profile_picture);
                        hideWalletOptions();
                    } else {
                        verificationErrorDisplay.textContent = data.error || 'Verification failed. Please try again.';
                        verificationErrorDisplay.classList.remove('hidden');
                        // If the code has expired, allow the user to restart signup
                        if (data.error === 'Verification code has expired. Please start the signup process again.') {
                            const restartLink = document.createElement('a');
                            restartLink.href = '#';
                            restartLink.textContent = ' Restart Signup';
                            restartLink.className = 'text-primary hover:underline';
                            restartLink.addEventListener('click', (e) => {
                                e.preventDefault();
                                verificationForm.remove();
                                showSignupForm();
                            });
                            verificationErrorDisplay.appendChild(restartLink);
                        }
                    }
                } catch (error) {
                    console.error('Email verification error:', error);
                    verificationErrorDisplay.textContent = 'An error occurred during verification. Please try again.';
                    verificationErrorDisplay.classList.remove('hidden');
                } finally {
                    hideLoadingIndicator();
                }
            });
        }

        function showPasswordResetForm() {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const walletTabContent = document.getElementById('wallet-tab-content');
            const loginTabContent = document.getElementById('login-tab-content');

            walletTabContent.classList.add('hidden', 'opacity-0');
            loginTabContent.classList.add('hidden', 'opacity-0');

            const email = loginTabContent.querySelector('input[name="email"]').value;
            if (!email || !emailRegex.test(email)) {
                const loginErrorDisplay = loginTabContent.querySelector('#login-error-display');
                loginErrorDisplay.textContent = 'Please enter a valid email to reset your password.';
                loginErrorDisplay.classList.remove('hidden');
                loginTabContent.classList.remove('hidden');
                setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
                return;
            }

            const resetForm = document.createElement('div');
            resetForm.id = 'reset-tab-content';
            resetForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            resetForm.innerHTML = `
                <div id="reset-methods" class="text-center">
                    <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">Select a method to reset your password for <span class="font-bold">${email}</span></p>
                    <p id="reset-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
                    <div id="reset-options" class="space-y-2"></div>
                    <p class="text-center text-xs mt-2">
                        Back to <a href="#" class="text-primary hover:underline" id="back-to-login-from-reset">Log in</a>
                    </p>
                </div>
            `;

            tabContentContainer.appendChild(resetForm);

            const resetErrorDisplay = resetForm.querySelector('#reset-error-display');
            const resetOptions = resetForm.querySelector('#reset-options');

            // Fetch available reset methods
            fetch('/wallet/initiate-password-reset/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ email })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        const methods = data.methods;
                        if (methods.wallet) {
                            const walletOption = document.createElement('button');
                            walletOption.className = 'w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto';
                            walletOption.textContent = 'Use Connected Wallet';
                            walletOption.addEventListener('click', () => showWalletResetForm(email));
                            resetOptions.appendChild(walletOption);
                        }
                        if (methods.email) {
                            const emailOption = document.createElement('button');
                            emailOption.className = 'w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto';
                            emailOption.textContent = 'Send Code to Email';
                            emailOption.addEventListener('click', () => showEmailResetForm(email));
                            resetOptions.appendChild(emailOption);
                        }
                    } else {
                        resetErrorDisplay.textContent = data.error || 'Failed to initiate password reset.';
                        resetErrorDisplay.classList.remove('hidden');
                    }
                })
                .catch(error => {
                    console.error('Error initiating password reset:', error);
                    resetErrorDisplay.textContent = 'An error occurred. Please try again.';
                    resetErrorDisplay.classList.remove('hidden');
                });

            const backToLoginLink = resetForm.querySelector('#back-to-login-from-reset');
            backToLoginLink.addEventListener('click', (e) => {
                e.preventDefault();
                resetForm.remove();
                loginTabContent.classList.remove('hidden');
                setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
            });
        }

        function showWalletResetForm(email) {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const resetMethods = document.getElementById('reset-methods');

            resetMethods.classList.add('hidden', 'opacity-0');

            const walletResetForm = document.createElement('div');
            walletResetForm.id = 'wallet-reset-form';
            walletResetForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            walletResetForm.innerHTML = `
                <div class="text-center">
                    <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">Sign a message with your connected wallet to reset your password.</p>
                    <button id="sign-wallet-reset" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Sign with Wallet</button>
                    <p id="wallet-reset-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
                    <p class="text-center text-xs mt-2">
                        Back to <a href="#" class="text-primary hover:underline" id="back-to-reset-methods">Reset Options</a>
                    </p>
                </div>
            `;

            tabContentContainer.appendChild(walletResetForm);

            const signWalletButton = walletResetForm.querySelector('#sign-wallet-reset');
            const walletResetErrorDisplay = walletResetForm.querySelector('#wallet-reset-error-display');

            signWalletButton.addEventListener('click', async () => {
                try {
                    showLoadingIndicator();

                    const user = await fetch('/wallet/initiate-password-reset/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ email })
                    }).then(res => res.json());

                    if (user.status !== 'success') {
                        throw new Error(user.error || 'Failed to fetch user data');
                    }

                    const publicKey = user.public_key;
                    const messageText = `Sign this message to reset your password. Wallet: ${publicKey}`;
                    const message = new TextEncoder().encode(messageText);

                    const wallet = wallets.find(w => w.isInstalled && w.provider.isConnected);
                    if (!wallet) {
                        throw new Error('No connected wallet found');
                    }

                    let signedMessage;
                    if (wallet.name === 'Solflare') {
                        const signatureData = await wallet.provider.signMessage(message);
                        signedMessage = Array.from(signatureData);
                    } else {
                        const signatureData = await wallet.provider.signMessage(message, 'utf8');
                        signedMessage = Array.from(signatureData.signature);
                    }

                    const signatureArray = new Uint8Array(signedMessage);
                    const signatureBase64 = btoa(String.fromCharCode.apply(null, signatureArray));

                    await fetch('/wallet/store-signed-message/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ signed_message: signatureBase64 })
                    });

                    showNewPasswordForm(email, 'wallet');
                } catch (error) {
                    console.error('Error signing message for password reset:', error);
                    walletResetErrorDisplay.textContent = 'Failed to sign message. Please try again.';
                    walletResetErrorDisplay.classList.remove('hidden');
                } finally {
                    hideLoadingIndicator();
                }
            });

            const backToResetMethodsLink = walletResetForm.querySelector('#back-to-reset-methods');
            backToResetMethodsLink.addEventListener('click', (e) => {
                e.preventDefault();
                walletResetForm.remove();
                resetMethods.classList.remove('hidden');
                setTimeout(() => resetMethods.classList.remove('opacity-0'), 10);
            });
        }

        function showEmailResetForm(email) {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const resetMethods = document.getElementById('reset-methods');

            resetMethods.classList.add('hidden', 'opacity-0');

            const emailResetForm = document.createElement('div');
            emailResetForm.id = 'email-reset-form';
            emailResetForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            emailResetForm.innerHTML = `
                <div class="text-center">
                    <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">We will send a verification code to your email.</p>
                    <button id="send-reset-code" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Send Code</button>
                    <p id="email-reset-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
                    <p class="text-center text-xs mt-2">
                        Back to <a href="#" class="text-primary hover:underline" id="back-to-reset-methods-email">Reset Options</a>
                    </p>
                </div>
            `;

            tabContentContainer.appendChild(emailResetForm);

            const sendResetCodeButton = emailResetForm.querySelector('#send-reset-code');
            const emailResetErrorDisplay = emailResetForm.querySelector('#email-reset-error-display');

            sendResetCodeButton.addEventListener('click', async () => {
                try {
                    showLoadingIndicator();

                    const response = await fetch('/wallet/send-password-reset-code/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ email })
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        showCodeVerificationForm(email);
                    } else {
                        emailResetErrorDisplay.textContent = data.error || 'Failed to send code. Please try again.';
                        emailResetErrorDisplay.classList.remove('hidden');
                    }
                } catch (error) {
                    console.error('Error sending reset code:', error);
                    emailResetErrorDisplay.textContent = 'An error occurred. Please try again.';
                    emailResetErrorDisplay.classList.remove('hidden');
                } finally {
                    hideLoadingIndicator();
                }
            });

            const backToResetMethodsLink = emailResetForm.querySelector('#back-to-reset-methods-email');
            backToResetMethodsLink.addEventListener('click', (e) => {
                e.preventDefault();
                emailResetForm.remove();
                resetMethods.classList.remove('hidden');
                setTimeout(() => resetMethods.classList.remove('opacity-0'), 10);
            });
        }

        function showCodeVerificationForm(email) {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const emailResetForm = document.getElementById('email-reset-form');

            emailResetForm.classList.add('hidden', 'opacity-0');

            const codeForm = document.createElement('div');
            codeForm.id = 'code-verification-form';
            codeForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            codeForm.innerHTML = `
                <div class="text-center">
                    <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">Enter the verification code sent to your email.</p>
                    <input type="text" id="reset-code" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50 mb-2" placeholder="Enter code" required>
                    <button id="verify-reset-code" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Verify Code</button>
                    <p id="code-verification-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
                    <p class="text-center text-xs mt-2">
                        Back to <a href="#" class="text-primary hover:underline" id="back-to-email-reset">Reset Options</a>
                    </p>
                </div>
            `;

            tabContentContainer.appendChild(codeForm);

            const verifyCodeButton = codeForm.querySelector('#verify-reset-code');
            const codeInput = codeForm.querySelector('#reset-code');
            const codeErrorDisplay = codeForm.querySelector('#code-verification-error-display');

            verifyCodeButton.addEventListener('click', async () => {
                const code = codeInput.value.trim();
                if (!code) {
                    codeErrorDisplay.textContent = 'Please enter the verification code.';
                    codeErrorDisplay.classList.remove('hidden');
                    return;
                }

                try {
                    showLoadingIndicator();

                    const response = await fetch('/wallet/verify-password-reset-code/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ email, code })
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        showNewPasswordForm(email, 'code');
                    } else {
                        codeErrorDisplay.textContent = data.error || 'Invalid or expired code.';
                        codeErrorDisplay.classList.remove('hidden');
                    }
                } catch (error) {
                    console.error('Error verifying code:', error);
                    codeErrorDisplay.textContent = 'An error occurred. Please try again.';
                    codeErrorDisplay.classList.remove('hidden');
                } finally {
                    hideLoadingIndicator();
                }
            });

            const backToEmailResetLink = codeForm.querySelector('#back-to-email-reset');
            backToEmailResetLink.addEventListener('click', (e) => {
                e.preventDefault();
                codeForm.remove();
                emailResetForm.classList.remove('hidden');
                setTimeout(() => emailResetForm.classList.remove('opacity-0'), 10);
            });
        }

        function showNewPasswordForm(email, method) {
            const tabContentContainer = document.querySelector('.tab-content-container');
            const walletResetForm = document.getElementById('wallet-reset-form');
            const codeForm = document.getElementById('code-verification-form');

            if (walletResetForm) walletResetForm.classList.add('hidden', 'opacity-0');
            if (codeForm) codeForm.classList.add('hidden', 'opacity-0');

            const newPasswordForm = document.createElement('div');
            newPasswordForm.id = 'new-password-form';
            newPasswordForm.className = 'tab-content transition-opacity duration-500 opacity-100';
            newPasswordForm.innerHTML = `
                <div class="text-center">
                    <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">Enter your new password.</p>
                    <div class="mb-2">
                        <label for="new-password" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1">New Password</label>
                        <div class="relative">
                            <input type="password" id="new-password" name="new_password" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                            <i class="fas fa-lock absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                        </div>
                        <p id="new-password-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
                    </div>
                    <button id="submit-new-password" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Reset Password</button>
                    <p id="new-password-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
                    <p class="text-center text-xs mt-2">
                        Back to <a href="#" class="text-primary hover:underline" id="back-to-login-from-new-password">Log in</a>
                    </p>
                </div>
            `;

            tabContentContainer.appendChild(newPasswordForm);

            const submitNewPasswordButton = newPasswordForm.querySelector('#submit-new-password');
            const newPasswordInput = newPasswordForm.querySelector('#new-password');
            const newPasswordError = newPasswordForm.querySelector('#new-password-error');
            const newPasswordErrorDisplay = newPasswordForm.querySelector('#new-password-error-display');

            submitNewPasswordButton.addEventListener('click', async () => {
                const newPassword = newPasswordInput.value.trim();
                if (!validatePassword(newPassword, newPasswordError)) {
                    return;
                }

                try {
                    showLoadingIndicator();

                    const url = method === 'wallet' ? '/wallet/reset-password-with-wallet/' : '/wallet/reset-password-with-code/';
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify({ email, new_password: newPassword })
                    });

                    const data = await response.json();
                    if (data.status === 'success') {
                        newPasswordForm.innerHTML = `
                            <div class="text-center">
                                <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">${data.message}</p>
                                <p class="text-center text-xs mt-2">
                                    Return to <a href="#" class="text-primary hover:underline" id="back-to-login-from-success">Log in</a>
                                </p>
                            </div>
                        `;
                        const backToLoginLink = newPasswordForm.querySelector('#back-to-login-from-success');
                        backToLoginLink.addEventListener('click', (e) => {
                            e.preventDefault();
                            newPasswordForm.remove();
                            loginTabContent.classList.remove('hidden');
                            setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
                        });
                    } else {
                        newPasswordErrorDisplay.textContent = data.error || 'Failed to reset password.';
                        newPasswordErrorDisplay.classList.remove('hidden');
                    }
                } catch (error) {
                    console.error('Error resetting password:', error);
                    newPasswordErrorDisplay.textContent = 'An error occurred. Please try again.';
                    newPasswordErrorDisplay.classList.remove('hidden');
                } finally {
                    hideLoadingIndicator();
                }
            });

            const backToLoginLink = newPasswordForm.querySelector('#back-to-login-from-new-password');
            backToLoginLink.addEventListener('click', (e) => {
                e.preventDefault();
                newPasswordForm.remove();
                loginTabContent.classList.remove('hidden');
                setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
            });
        }
    } catch (error) {
        console.error('Initialization error in wallet-connection.js:', error);
        handleError(error, 'Failed to initialize wallet connection system');
    }

    // Function to show the Google signup form
    function showGoogleSignupForm(googleData) {
        const tabContentContainer = document.querySelector('.tab-content-container');
        const walletTabContent = document.getElementById('wallet-tab-content');
        const loginTabContent = document.getElementById('login-tab-content');

        walletTabContent.classList.add('hidden', 'opacity-0');
        loginTabContent.classList.add('hidden', 'opacity-0');

        const googleSignupForm = document.createElement('div');
        googleSignupForm.id = 'google-signup-form';
        googleSignupForm.className = 'tab-content transition-opacity duration-500 opacity-100';
        googleSignupForm.innerHTML = `
        <div class="text-center">
            <p class="text-xs font-roboto text-text-light dark:text-text-dark mb-2">Complete your signup with Google</p>
            <div class="mb-2">
                <label for="google-email" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1">Email (from Google)</label>
                <div class="relative">
                    <input type="email" id="google-email" name="email" value="${googleData.email || ''}" readonly class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm bg-gray-200 dark:bg-gray-600 text-text-light dark:text-text-dark text-xs">
                    <i class="fas fa-envelope absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
            </div>
            <div class="mb-2">
                <label for="google-username" class="block text-xs font-roboto font-medium text-text-light dark:text-text-dark mb-1">Choose a Username</label>
                <div class="relative">
                    <input type="text" id="google-username" name="username" value="${googleData.email ? googleData.email.split('@')[0] : ''}" class="w-full px-2 py-1 border border-primary/30 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary bg-white dark:bg-gray-700 text-text-light dark:text-text-dark text-xs transition-all duration-300 hover:border-primary/50" required>
                    <i class="fas fa-user absolute right-2 top-1/2 transform -translate-y-1/2 text-primary text-sm"></i>
                </div>
                <p id="google-username-error" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in"></p>
            </div>
            <button id="submit-google-signup" class="w-full bg-primary text-white px-3 py-1 rounded-lg hover:bg-primary-dark transition-all duration-300 font-semibold text-xs font-roboto">Sign Up with Google</button>
            <p id="google-signup-error-display" class="text-red-500 text-xs mt-1 hidden font-roboto animate-fade-in text-center"></p>
            <p class="text-center text-xs mt-2">
                Back to <a href="#" class="text-primary hover:underline" id="back-to-login-from-google-signup">Log in</a>
            </p>
        </div>
    `;

        tabContentContainer.appendChild(googleSignupForm);

        const submitGoogleSignupButton = googleSignupForm.querySelector('#submit-google-signup');
        const usernameInput = googleSignupForm.querySelector('#google-username');
        const usernameError = googleSignupForm.querySelector('#google-username-error');
        const signupErrorDisplay = googleSignupForm.querySelector('#google-signup-error-display');

        submitGoogleSignupButton.addEventListener('click', async () => {
            const username = usernameInput.value.trim();
            if (!username) {
                usernameError.textContent = 'Please enter a username.';
                usernameError.classList.remove('hidden');
                return;
            }

            try {
                showLoadingIndicator();

                const formData = new FormData();
                formData.append('username', username);
                formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

                const response = await fetch('/wallet/google-signup/', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                if (data.status === 'success') {
                    // console.log("Google signup successful");
                    isWalletConnected = true; // Use local variable instead of window.isWalletConnected
                    updateHeaderWalletState(true, data.username, data.profile_picture);
                    hideWalletOptions();
                } else {
                    signupErrorDisplay.textContent = data.error || 'Signup failed. Please try again.';
                    signupErrorDisplay.classList.remove('hidden');
                }
            } catch (error) {
                console.error('Google signup error:', error);
                signupErrorDisplay.textContent = 'An error occurred during signup. Please try again.';
                signupErrorDisplay.classList.remove('hidden');
            } finally {
                hideLoadingIndicator();
            }
        });

        const backToLoginLink = googleSignupForm.querySelector('#back-to-login-from-google-signup');
        backToLoginLink.addEventListener('click', (e) => {
            e.preventDefault();
            googleSignupForm.remove();
            loginTabContent.classList.remove('hidden');
            setTimeout(() => loginTabContent.classList.remove('opacity-0'), 10);
        });
    }
});