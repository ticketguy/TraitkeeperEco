// console.log("solana-stats.js loaded");

// Variable to store the previous Solana price (no longer needed, but keeping for potential future use)
let previousPrice = null;

// Function to fetch and update Solana price and TPS
function updateSolanaStats() {
    // console.log("Running updateSolanaStats");

    // Find DOM elements
    const priceElement = document.querySelector('.solana-price .price-value');
    const tpsElement = document.querySelector('.solana-tps');

    if (!priceElement || !tpsElement) {
        console.error("Price or TPS element not found in DOM");
        // console.log("Price element:", priceElement);
        // console.log("TPS element:", tpsElement);
        return;
    }

    // Apply fade animation to stats
    priceElement.classList.add('animate-fade-pulse');
    tpsElement.classList.add('animate-fade-pulse');

    // console.log("Making fetch request to /api/solana-network-stats/");
    fetch('/api/solana-network-stats/')
        .then(response => {
            // console.log("Fetch response received:", response);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            // console.log('API Response:', data);

            // Update Solana price with 24-hour change
            if (priceElement) {
                const newPrice = data?.price?.price_usd;
                const change24h = data?.price?.change_24h_percent;

                // Validate newPrice and change24h
                if (typeof newPrice !== 'number' || isNaN(newPrice)) {
                    console.error("Invalid price_usd value:", newPrice);
                    priceElement.textContent = 'N/A';
                    return;
                }
                if (typeof change24h !== 'number' || isNaN(change24h)) {
                    console.error("Invalid change_24h_percent value:", change24h);
                    priceElement.textContent = `$${newPrice.toFixed(2)} (N/A)`;
                    return;
                }

                // Format the display: price (24h change)
                const priceText = `$${newPrice.toFixed(2)}`;
                const change24hFormatted = change24h >= 0 ? `+${change24h.toFixed(1)}%` : `${change24h.toFixed(1)}%`;

                // Determine color and arrow based on 24-hour change
                const isPositive = change24h >= 0; // Default to green if change is 0
                const arrow = isPositive ? '↑' : '↓';
                const changeClass = isPositive
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700';

                // Update the price element with styled spans
                priceElement.innerHTML = `
                    <span class="text-sm">${priceText}</span>
                    <span class="text-xs ${changeClass} px-1.5 py-0.5 rounded mx-1">
                        ${arrow} ${change24hFormatted}
                    </span>
                `;

                // Set the overall color of the price element
                priceElement.classList.remove('text-red-500', 'text-green-500');
                priceElement.classList.add(isPositive ? 'text-green-500' : 'text-red-500');

                previousPrice = newPrice;  // Update the previous price (for potential future use)
            }

            // Update Solana TPS
            if (tpsElement) {
                const averageTps = data?.tps?.average_tps;
                if (typeof averageTps === 'number' && !isNaN(averageTps)) {
                    tpsElement.textContent = `${averageTps.toFixed(2)} TPS`;
                } else {
                    console.error("Invalid average_tps value:", averageTps);
                    tpsElement.textContent = 'TPS: N/A';
                }
            }
        })
        .catch(error => {
            console.error('Error fetching Solana stats:', error);
            if (priceElement) priceElement.textContent = 'Error';
            if (tpsElement) tpsElement.textContent = 'TPS: Error';
        });
}

// Function to initialize the updateSolanaStats with retries
function initializeSolanaStats(retries = 3, delay = 1000) {
    // console.log("Initializing Solana stats");

    // Check if DOM elements are available
    const priceElement = document.querySelector('.solana-price .price-value');
    const tpsElement = document.querySelector('.solana-tps');

    if (!priceElement || !tpsElement) {
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

    // Refresh every 30 seconds
    setInterval(() => {
        // console.log("Polling for updated Solana stats");
        updateSolanaStats();
    }, 30000);
}

// Run initialization with retries
document.addEventListener("DOMContentLoaded", () => {
    // console.log("DOMContentLoaded event fired in solana-stats.js, running initializeSolanaStats");
    initializeSolanaStats();
});

// Fallback: Run initialization immediately in case DOMContentLoaded doesn't fire
// console.log("Running initializeSolanaStats as fallback in solana-stats.js");
initializeSolanaStats();