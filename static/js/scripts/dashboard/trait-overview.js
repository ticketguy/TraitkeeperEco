// Sample data - replace with actual data from your backend
const nfts = [
    { id: 1, name: 'NFT 1', image: 'nft1.jpg', traits: { color: 'red', shape: 'circle', size: 'large' } },
    { id: 2, name: 'NFT 2', image: 'nft2.jpg', traits: { color: 'blue', shape: 'square', size: 'medium' } },
    { id: 3, name: 'NFT 3', image: 'nft3.jpg', traits: { color: 'green', shape: 'triangle', size: 'small' } },
    // Add more NFTs as needed
];

// Calculate trait rarity
function calculateTraitRarity() {
    const traitCounts = {};
    nfts.forEach(nft => {
        Object.entries(nft.traits).forEach(([trait, value]) => {
            if (!traitCounts[trait]) traitCounts[trait] = {};
            if (!traitCounts[trait][value]) traitCounts[trait][value] = 0;
            traitCounts[trait][value]++;
        });
    });

    const traitRarity = {};
    Object.entries(traitCounts).forEach(([trait, values]) => {
        traitRarity[trait] = {};
        Object.entries(values).forEach(([value, count]) => {
            traitRarity[trait][value] = (count / nfts.length * 100).toFixed(2) + '%';
        });
    });

    return traitRarity;
}

// Display NFTs
function displayNFTs() {
    const grid = document.getElementById('nftGrid');
    grid.innerHTML = ''; // Clear existing content
    const traitRarity = calculateTraitRarity();

    nfts.forEach(nft => {
        const card = document.createElement('div');
        card.className = 'nft-card';
        card.innerHTML = `
            <h3>${nft.name}</h3>
            <img src="${nft.image}" alt="${nft.name}" style="width:100%; height:auto;">
            <ul class="trait-list">
                ${Object.entries(nft.traits).map(([trait, value]) => `
                    <li class="trait-item">
                        <span>${trait}: ${value}</span>
                        <span class="trait-rarity">${traitRarity[trait][value]}</span>
                    </li>
                `).join('')}
            </ul>
            <button class="expand-btn">Show More</button>
            <div class="expanded-info">
                <p>Owner: 0x1234...5678</p>
                <p>Last Sale: 1.5 ETH</p>
                <p>Rank: #123 / 10000</p>
            </div>
        `;

        const expandBtn = card.querySelector('.expand-btn');
        const expandedInfo = card.querySelector('.expanded-info');
        expandBtn.addEventListener('click', () => {
            if (expandedInfo.style.display === 'block') {
                expandedInfo.style.display = 'none';
                expandBtn.textContent = 'Show More';
            } else {
                expandedInfo.style.display = 'block';
                expandBtn.textContent = 'Show Less';
            }
        });

        grid.appendChild(card);
    });
}

// Update stats summary
function updateStatsSummary() {
    document.getElementById('total-nfts').textContent = nfts.length;

    const uniqueTraits = new Set();
    nfts.forEach(nft => {
        Object.keys(nft.traits).forEach(trait => uniqueTraits.add(trait));
    });
    document.getElementById('unique-traits').textContent = uniqueTraits.size;

    const traitRarity = calculateTraitRarity();
    let rarestTrait = { trait: '', value: '', rarity: 100 };
    Object.entries(traitRarity).forEach(([trait, values]) => {
        Object.entries(values).forEach(([value, rarity]) => {
            const rarityValue = parseFloat(rarity);
            if (rarityValue < rarestTrait.rarity) {
                rarestTrait = { trait, value, rarity: rarityValue };
            }
        });
    });
    document.getElementById('rarest-trait').textContent = `${rarestTrait.trait}: ${rarestTrait.value} (${rarestTrait.rarity.toFixed(2)}%)`;
}

// Search functionality
document.getElementById('nft-search').addEventListener('input', function() {
    const searchTerm = this.value.toLowerCase();
    const filteredNFTs = nfts.filter(nft => 
        nft.name.toLowerCase().includes(searchTerm) ||
        Object.values(nft.traits).some(value => value.toLowerCase().includes(searchTerm))
    );
    displayFilteredNFTs(filteredNFTs);
});

// Sort functionality
document.getElementById('trait-sort').addEventListener('change', function() {
    const sortType = this.value;
    let sortedNFTs;
    if (sortType === 'name') {
        sortedNFTs = [...nfts].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortType === 'rarity') {
        const traitRarity = calculateTraitRarity();
        sortedNFTs = [...nfts].sort((a, b) => {
            const aRarity = Object.values(a.traits).reduce((acc, val) => acc * parseFloat(traitRarity[val]), 1);
            const bRarity = Object.values(b.traits).reduce((acc, val) => acc * parseFloat(traitRarity[val]), 1);
            return aRarity - bRarity;
        });
    }
    displayFilteredNFTs(sortedNFTs);
});

function displayFilteredNFTs(filteredNFTs) {
    const grid = document.getElementById('nftGrid');
    grid.innerHTML = ''; // Clear existing content
    const traitRarity = calculateTraitRarity();

    filteredNFTs.forEach(nft => {
        // ... (use the same card creation logic as in the displayNFTs function)
    });
}

// Initialize the trait overview
function initTraitOverview() {
    displayNFTs();
    updateStatsSummary();
}

// Run initialization when the page loads
window.onload = function() {
    initTraitOverview();
    // ... (keep other init functions)
};