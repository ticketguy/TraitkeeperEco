// console.log("solana-stats.js loaded");

// Variable to store the previous Solana price (no longer needed, but keeping for potential future use)
let previousPrice = null;

// Function to fetch and update Solana price and TPS
function updateSolanaStats() {
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

                previousPrice = newPrice;  // Update the previous price (for potential future use)
            }

            // Update Solana TPS
            if (tpsElement) {
                const averageTps = data?.tps?.average_tps;
                if (typeof averageTps === 'number' && !isNaN(averageTps)) {
                    tpsElement.textContent = averageTps.toFixed(0);
                } else {
                    console.error("Invalid average_tps value:", averageTps);
                    tpsElement.textContent = 'N/A';
                }
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
            if (priceElement) priceElement.textContent = 'Error';
            if (tpsElement) tpsElement.textContent = 'Error';
            priceElements.forEach(el => el.textContent = 'Error');
            tpsElements.forEach(el => el.textContent = 'TPS: Error');
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