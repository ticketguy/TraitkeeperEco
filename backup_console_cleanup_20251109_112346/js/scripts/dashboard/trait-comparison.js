// ... (keep your existing code) ...

// Trait Comparison Tool
let selectedNFTs = [];

function initTraitComparisonTool() {
    populateNFTSelectors();
    document.getElementById('addNftBtn').addEventListener('click', addNFTSelector);
    document.getElementById('compareBtn').addEventListener('click', compareNFTs);
    document.getElementById('comparisonType').addEventListener('change', updateComparisonView);
}

function populateNFTSelectors() {
    const selectors = document.querySelectorAll('.nft-select');
    selectors.forEach(selector => {
        nfts.forEach(nft => {
            const option = document.createElement('option');
            option.value = nft.id;
            option.textContent = nft.name;
            selector.appendChild(option);
        });
    });
}

function addNFTSelector() {
    const nftSelector = document.querySelector('.nft-selector');
    const newSelect = document.createElement('select');
    newSelect.className = 'nft-select';
    newSelect.innerHTML = '<option value="">Select NFT</option>';
    populateNFTSelectors();
    nftSelector.insertBefore(newSelect, document.getElementById('addNftBtn'));
}

function compareNFTs() {
    selectedNFTs = Array.from(document.querySelectorAll('.nft-select'))
        .map(select => nfts.find(nft => nft.id == select.value))
        .filter(nft => nft); // Remove any undefined values

    if (selectedNFTs.length < 2) {
        alert('Please select at least two NFTs to compare.');
        return;
    }

    updateComparisonView();
    analyzeTraits();
}

function updateComparisonView() {
    const comparisonType = document.getElementById('comparisonType').value;
    document.querySelectorAll('.comparison-view').forEach(view => view.style.display = 'none');

    switch (comparisonType) {
        case 'sideBySide':
            showSideBySideComparison();
            break;
        case 'traitDistribution':
            showTraitDistribution();
            break;
        case 'radarChart':
            showRadarChart();
            break;
    }
}

function showSideBySideComparison() {
    const container = document.getElementById('sideBySideComparison');
    container.style.display = 'flex';
    container.innerHTML = '';

    selectedNFTs.forEach(nft => {
        const card = document.createElement('div');
        card.className = 'nft-comparison-card';
        card.innerHTML = `
            <h3>${nft.name}</h3>
            <img src="${nft.image}" alt="${nft.name}" style="width:100%; height:auto;">
            <ul>
                ${Object.entries(nft.traits).map(([trait, value]) => `
                    <li>${trait}: ${value}</li>
                `).join('')}
            </ul>
        `;
        container.appendChild(card);
    });

    highlightDifferences();
}

function highlightDifferences() {
    const traitLists = document.querySelectorAll('.nft-comparison-card ul');
    const allTraits = new Set(selectedNFTs.flatMap(nft => Object.keys(nft.traits)));

    allTraits.forEach(trait => {
        const traitValues = selectedNFTs.map(nft => nft.traits[trait]);
        const allSame = traitValues.every(value => value === traitValues[0]);

        if (!allSame) {
            traitLists.forEach((list, index) => {
                const traitItem = Array.from(list.children).find(li => li.textContent.startsWith(trait));
                if (traitItem) {
                    traitItem.classList.add('trait-diff');
                }
            });
        }
    });
}

function showTraitDistribution() {
    const container = document.getElementById('traitDistributionChart');
    container.style.display = 'block';
    container.innerHTML = '';

    const allTraits = new Set(selectedNFTs.flatMap(nft => Object.keys(nft.traits)));

    allTraits.forEach(trait => {
        const traitValues = selectedNFTs.map(nft => nft.traits[trait]);
        const valueCounts = traitValues.reduce((acc, value) => {
            acc[value] = (acc[value] || 0) + 1;
            return acc;
        }, {});

        const chartContainer = document.createElement('div');
        chartContainer.style.marginBottom = '20px';
        const canvas = document.createElement('canvas');
        chartContainer.appendChild(canvas);
        container.appendChild(chartContainer);

        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: Object.keys(valueCounts),
                datasets: [{
                    label: trait,
                    data: Object.values(valueCounts),
                    backgroundColor: 'rgba(75, 192, 192, 0.6)'
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    });
}

function showRadarChart() {
    const canvas = document.getElementById('radarChart');
    canvas.style.display = 'block';
    const ctx = canvas.getContext('2d');

    const allTraits = new Set(selectedNFTs.flatMap(nft => Object.keys(nft.traits)));
    const traitValues = Array.from(allTraits).reduce((acc, trait) => {
        acc[trait] = selectedNFTs.map(nft => nft.traits[trait]);
        return acc;
    }, {});

    const data = {
        labels: Array.from(allTraits),
        datasets: selectedNFTs.map((nft, index) => ({
            label: nft.name,
            data: Array.from(allTraits).map(trait => {
                const value = nft.traits[trait];
                return isNaN(value) ? traitValues[trait].indexOf(value) : parseFloat(value);
            }),
            fill: true,
            backgroundColor: `rgba(75, 192, 192, ${0.2 + index * 0.1})`,
            borderColor: `rgb(75, 192, 192)`,
            pointBackgroundColor: `rgb(75, 192, 192)`,
            pointBorderColor: '#fff',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: `rgb(75, 192, 192)`
        }))
    };

    new Chart(ctx, {
        type: 'radar',
        data: data,
        options: {
            elements: {
                line: {
                    borderWidth: 3
                }
            }
        }
    });
}

function analyzeTraits() {
    const container = document.getElementById('traitAnalysisResults');
    container.innerHTML = '';

    const allTraits = new Set(selectedNFTs.flatMap(nft => Object.keys(nft.traits)));
    const traitRarity = calculateTraitRarity();

    allTraits.forEach(trait => {
        const traitValues = selectedNFTs.map(nft => nft.traits[trait]);
        const uniqueValues = new Set(traitValues);

        let analysis = `<h4>${trait}</h4>`;
        if (uniqueValues.size === 1) {
            analysis += `<p>All selected NFTs have the same value: ${traitValues[0]} (Rarity: ${traitRarity[trait][traitValues[0]]})</p>`;
        } else {
            analysis += `<p>Values differ across NFTs:</p><ul>`;
            uniqueValues.forEach(value => {
                const count = traitValues.filter(v => v === value).length;
                analysis += `<li>${value}: ${count} NFT(s) (Rarity: ${traitRarity[trait][value]})</li>`;
            });
            analysis += '</ul>';
        }

        container.innerHTML += analysis;
    });
}

// Run initialization when the page loads
window.onload = function() {
    initTraitOverview();
    initTraitComparisonTool();
    // ... (keep other init functions)
};


function compareNFTs() {
    const nft1 = document.getElementById('nft1').value;
    const nft2 = document.getElementById('nft2').value;
    const results = document.getElementById('comparisonResults');
    results.innerHTML = `Comparing ${nft1} and ${nft2}`;
    // Implement actual comparison logic here
}