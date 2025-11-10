// Data Visualization
const ctx = document.getElementById('nftChart').getContext('2d');
const chartInfo = document.getElementById('chartInfo');

const chartData = {
    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    datasets: [{
        label: 'NFT Sales',
        data: [12, 19, 3, 5, 2, 3],
        backgroundColor: 'rgba(98, 0, 238, 0.2)',
        borderColor: 'rgba(98, 0, 238, 1)',
        borderWidth: 1
    }]
};

const chart = new Chart(ctx, {
    type: 'bar',
    data: chartData,
    options: {
        scales: {
            y: {
                beginAtZero: true
            }
        },
        onClick: (event, elements) => {
            if (elements.length > 0) {
                const dataIndex = elements[0].index;
                const value = chartData.datasets[0].data[dataIndex];
                chartInfo.textContent = `${chartData.labels[dataIndex]}: ${value} sales`;
            }
        }
    }
});

// Recent Activity Feed
const activityFeed = document.getElementById('activityFeed');

function addActivity(activity) {
    const li = document.createElement('li');
    li.innerHTML = `
        <span class="activity-icon">🔔</span>
        <div>
            <p>${activity.description}</p>
            <p class="time">${activity.time}</p>
        </div>
    `;
    activityFeed.prepend(li);
    if (activityFeed.children.length > 5) {
        activityFeed.removeChild(activityFeed.lastChild);
    }
}

setInterval(() => {
    const activities = [
        { description: "NFT #1234 sold for 2.5 ETH", time: "Just now" },
        { description: "NFT #5678 listed for 1.8 ETH", time: "Just now" },
        { description: "User0x123 bought 3 NFTs", time: "Just now" }
    ];
    const randomActivity = activities[Math.floor(Math.random() * activities.length)];
    addActivity(randomActivity);
}, 5000);

// Featured NFT Carousel
const nftCarousel = document.getElementById('nftCarousel');
const prevButton = document.getElementById('prevNFT');
const nextButton = document.getElementById('nextNFT');

const nfts = [
    { name: "CryptoKitty #42", image: "placeholder-nft-1.png", price: "5.2 ETH" },
    { name: "Bored Ape #789", image: "placeholder-nft-2.png", price: "80 ETH" },
    { name: "Pudgy Penguin #101", image: "placeholder-nft-3.png", price: "3.7 ETH" }
];

let currentNFT = 0;

function renderNFT(index) {
    const nft = nfts[index];
    nftCarousel.innerHTML = `
        <div class="nft-item">
            <img src="${nft.image}" alt="${nft.name}">
            <h3>${nft.name}</h3>
            <p>Price: ${nft.price}</p>
        </div>
    `;
}

prevButton.addEventListener('click', () => {
    currentNFT = (currentNFT - 1 + nfts.length) % nfts.length;
    renderNFT(currentNFT);
});

nextButton.addEventListener('click', () => {
    currentNFT = (currentNFT + 1) % nfts.length;
    renderNFT(currentNFT);
});

renderNFT(currentNFT);

// Tooltips are handled by CSS, no JavaScript required
