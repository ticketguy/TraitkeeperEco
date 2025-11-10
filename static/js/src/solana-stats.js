// console.log("solana-stats.js loaded");

// Variable to store the previous Solana price (no longer needed, but keeping for potential future use)
let previousPrice = null;
let rateLimitBackoff = 0; // Track rate limit backoff time
let lastRequestTime = 0; // Track last request timestamp
let isRequestInProgress = false; // Prevent concurrent requests

// Function to fetch and update Solana price and TPS
function updateSolanaStats() {
    // Prevent concurrent requests
    if (isRequestInProgress) {
        console.log('Request already in progress, skipping...');
        return;
    }

    // Check if we're in a backoff period
    const now = Date.now();
    if (rateLimitBackoff > 0 && now - lastRequestTime < rateLimitBackoff) {
        console.log('Rate limited, waiting before next request...');
        return;
    }

    isRequestInProgress = true;
    // console.log("Running updateSolanaStats");

    // Find ALL DOM elements (both desktop and mobile)
    const priceElements = document.querySelectorAll('.solana-price .price-value');
    const tpsElements = document.querySelectorAll('.solana-tps');

    if (priceElements.length === 0 || tpsElements.length === 0) {
        console.error("Price or TPS elements not found in DOM");
        return;
    }

    // Apply fade animation to all stats
    priceElements.forEach(el => el.classList.add('animate-fade-pulse'));
    tpsElements.forEach(el => el.classList.add('animate-fade-pulse'));

    // console.log("Making fetch request to /api/solana-network-stats/");
    lastRequestTime = Date.now();

    fetch('/api/solana-network-stats/')
        .then(response => {
            // console.log("Fetch response received:", response);
            if (!response.ok) {
                if (response.status === 429) {
                    // Rate limited - implement exponential backoff
                    rateLimitBackoff = rateLimitBackoff === 0 ? 60000 : Math.min(rateLimitBackoff * 2, 300000); // Start at 1min, max 5min
                    console.warn(`Rate limited (429). Backing off for ${rateLimitBackoff / 1000}s`);
                    throw new Error(`Rate limited. Retry after ${rateLimitBackoff / 1000}s`);
                }
                throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
            }
            // Reset backoff on successful request
            rateLimitBackoff = 0;
            return response.json();
        })
        .then(data => {
            // console.log('API Response:', data);

            const newPrice = data?.price?.price_usd;
            const change24h = data?.price?.change_24h_percent;
            const averageTps = data?.tps?.average_tps;

            // Validate data
            if (typeof newPrice !== 'number' || isNaN(newPrice)) {
                console.error("Invalid price_usd value:", newPrice);
                priceElements.forEach(el => el.textContent = 'N/A');
                return;
            }
            if (typeof change24h !== 'number' || isNaN(change24h)) {
                console.error("Invalid change_24h_percent value:", change24h);
                priceElements.forEach(el => el.textContent = `$${newPrice.toFixed(2)} (N/A)`);
                return;
            }

            // Format the display: price (24h change)
            const priceText = `$${newPrice.toFixed(2)}`;
            const change24hFormatted = change24h >= 0 ? `+${change24h.toFixed(1)}%` : `${change24h.toFixed(1)}%`;

            // Determine color and arrow based on 24-hour change
            const isPositive = change24h >= 0;
            const arrow = isPositive ? '↑' : '↓';
            const changeClass = isPositive
                ? 'bg-green-100 text-green-700'
                : 'bg-red-100 text-red-700';

            // Update ALL price elements (both desktop and mobile)
            priceElements.forEach(priceElement => {
                priceElement.innerHTML = `
                    <span class="text-sm">${priceText}</span>
                    <span class="text-xs ${changeClass} px-1.5 py-0.5 rounded mx-1">
                        ${arrow} ${change24hFormatted}
                    </span>
                `;

                priceElement.classList.remove('text-red-500', 'text-green-500');
                priceElement.classList.add(isPositive ? 'text-green-500' : 'text-red-500');
            });

            // Update ALL TPS elements (both desktop and mobile)
            if (typeof averageTps === 'number' && !isNaN(averageTps)) {
                tpsElements.forEach(tpsElement => {
                    tpsElement.textContent = `${averageTps.toFixed(2)} TPS`;
                });
            } else {
                console.error("Invalid average_tps value:", averageTps);
                tpsElements.forEach(tpsElement => {
                    tpsElement.textContent = 'TPS: N/A';
                });
            }

            previousPrice = newPrice;
        })
        .catch(error => {
            console.error('Error fetching Solana stats:', error);
            priceElements.forEach(el => el.textContent = 'Error');
            tpsElements.forEach(el => el.textContent = 'TPS: Error');
        })
        .finally(() => {
            isRequestInProgress = false;
        });
}

// Function to initialize the updateSolanaStats with retries
function initializeSolanaStats(retries = 3, delay = 1000) {
    // console.log("Initializing Solana stats");

    // Check if DOM elements are available
    const priceElements = document.querySelectorAll('.solana-price .price-value');
    const tpsElements = document.querySelectorAll('.solana-tps');

    if (priceElements.length === 0 || tpsElements.length === 0) {
        if (retries > 0) {
            // console.log(`DOM elements not found, retrying in ${delay}ms... (${retries} retries left)`);
            setTimeout(() => initializeSolanaStats(retries - 1, delay * 2), delay);
        } else {
            console.error("DOM elements not found after retries, giving up");
        }
        return;
    }

    // Initial fetch
    // console.log("Calling updateSolanaStats initially");
    updateSolanaStats();

    // Refresh every 60 seconds (reduced from 30s to avoid rate limits)
    setInterval(() => {
        // console.log("Polling for updated Solana stats");
        updateSolanaStats();
    }, 60000);
}

// Run initialization with retries (only on DOMContentLoaded to avoid duplicate calls)
document.addEventListener("DOMContentLoaded", () => {
    // console.log("DOMContentLoaded event fired in solana-stats.js, running initializeSolanaStats");
    // Add random jitter (0-5s) to prevent multiple tabs hitting API simultaneously
    const jitter = Math.random() * 5000;
    setTimeout(() => {
        initializeSolanaStats();
    }, jitter);
});