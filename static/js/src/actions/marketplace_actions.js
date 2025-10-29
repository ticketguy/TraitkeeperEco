/**
 * TraitKeeper Marketplace Actions
 *
 * Handles client-side logic for:
 * - Placing private bids ("Make Offer")
 * - Executing purchases ("Buy Now" for Direct Sell or Accepting Asking Price)
 * - Fetching data for and populating the NFT detail modal.
 *
 * Assumes a global `window.traitkeeperConfig` object exists (defined in base.html)
 * containing:
 * - csrfToken
 * - apiEndpoints (placeBid, buyDirect, acceptAsk, getNftDetails - Note: getNftDetails needs base URL)
 * - isAuthenticated
 *
 * Assumes the presence of specific HTML elements and IDs defined in collection.html.
 */

document.addEventListener("DOMContentLoaded", function () {
  console.log("Marketplace Actions Script Loaded"); // Debug log

  // --- Configuration & Elements ---
  const config = window.traitkeeperConfig || {}; // Get config from global scope
  const csrfToken = config.csrfToken;
  const apiEndpoints = config.apiEndpoints || {};
  const isAuthenticated = config.isAuthenticated || false;

  const nftDetailModal = document.getElementById("nft-detail-modal");
  const nftsGridContainer = document.getElementById("nfts-grid");
  const closeNftModalBtn = document.getElementById("close-nft-modal");

  // --- Helper for API Calls ---
  async function callApi(endpoint, method = "GET", data = null) {
    if (!endpoint) {
      console.error("API endpoint not defined.");
      alert("Configuration error. Cannot perform action.");
      return null;
    }

    // Authentication check for POST requests (actions)
    if (method === "POST" && !isAuthenticated) {
      alert(
        "Please log in or connect your wallet to perform marketplace actions."
      );
      // Optionally, trigger the login/wallet modal here if you have access to its toggle function
      return null;
    }

    const headers = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (csrfToken && method === "POST") {
      headers["X-CSRFToken"] = csrfToken;
    }
    // Add Authorization header if needed (e.g., for DRF Token Auth)
    // if (config.authToken) {
    //     headers['Authorization'] = `Token ${config.authToken}`;
    // }

    const options = {
      method: method,
      headers: headers,
    };
    if (data && method !== "GET") {
      // Don't send body for GET
      options.body = JSON.stringify(data);
    }

    console.log(
      `Calling API: ${method} ${endpoint}`,
      data ? `with data: ${JSON.stringify(data)}` : ""
    );
    // Consider showing a global loading indicator here

    try {
      const response = await fetch(endpoint, options);

      let result;
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        result = await response.json();
        console.log(`API Response from ${endpoint}:`, result);
      } else {
        const text = await response.text();
        console.error("Non-JSON response received:", text);
        throw new Error(
          `Server returned non-JSON response. Status: ${response.status}`
        );
      }

      if (!response.ok || (result && result.success === false)) {
        throw new Error(
          result?.error || `HTTP error! Status: ${response.status}`
        );
      }

      // Return structure depends on API response format
      if (method === "GET" && result && result.success) {
        return result.details; // Assumes 'details' key for GET NFT data
      }
      if (method === "POST" && result && result.success) {
        return result.data; // Assumes 'data' key for POST action responses
      }
      // Fallback for unexpected success structure
      return result;
    } catch (error) {
      console.error(`Error calling ${endpoint}:`, error);
      alert(`Action failed: ${error.message}`); // User feedback
      return null;
    } finally {
      // Consider hiding the global loading indicator here
    }
  }

  // --- "Make Offer" Logic ---
  // FIXED: Attached to window to be globally accessible
  window.handleMakeOfferClick = function (event) {
    event.preventDefault();
    event.stopPropagation();

    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to make an offer.");
      return;
    }

    const nftCard = event.target.closest(".nft-card");
    let nftId;

    if (nftCard) {
      nftId = nftCard.dataset.nftId;
    } else if (nftDetailModal && !nftDetailModal.classList.contains("hidden")) {
      nftId = nftDetailModal.dataset.currentNftId;
    }

    if (!nftId) {
      console.error("Could not find NFT ID for offer.");
      alert("Could not determine which NFT to make an offer on.");
      return;
    }

    console.log("Make Offer clicked for NFT:", nftId);

    // Simple prompt (Replace with a dedicated offer modal UI)
    const bidAmountStr = prompt(
      `Enter your bid amount in SOL for NFT ${nftId.slice(0, 8)}...`
    );
    if (bidAmountStr === null) return; // User cancelled

    const bidAmount = parseFloat(bidAmountStr);
    if (isNaN(bidAmount) || bidAmount <= 0) {
      alert("Invalid bid amount. Please enter a positive number.");
      return;
    }

    // Call the backend API using the configured endpoint
    callApi(apiEndpoints.placeBid, "POST", {
      nft_mint: nftId,
      amount: bidAmount.toString(), // Send as string
      // expiry_hours: 72 // Optional
    }).then((result) => {
      if (result) {
        alert(
          `Offer placed successfully! Bid ID: ${result.bid_id.slice(0, 12)}...`
        );
        // If modal is open for this NFT, refresh its offers tab
        if (
          nftDetailModal &&
          !nftDetailModal.classList.contains("hidden") &&
          nftDetailModal.dataset.currentNftId === nftId
        ) {
          fetchAndPopulateOffers(nftId); // Refresh offers tab
        }
      }
    });
  };

  // --- "Buy Now" Logic ---
  function handleBuyNowClick(event) {
    event.preventDefault();
    event.stopPropagation();

    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to buy.");
      return;
    }

    const nftId = nftDetailModal ? nftDetailModal.dataset.currentNftId : null;
    const priceText = nftDetailModal
      ? nftDetailModal.querySelector("#modal-nft-price").textContent
      : "-- SOL";
    const isDirectSell = nftDetailModal
      ? nftDetailModal.dataset.isDirectSell === "true"
      : false;
    const isSellIntent = nftDetailModal
      ? nftDetailModal.dataset.isSellIntent === "true"
      : false;

    if (!nftId) {
      alert("Cannot determine which NFT to buy.");
      return;
    }

    if (
      !confirm(
        `Confirm purchase of NFT ${nftId.slice(0, 8)}... for ${priceText}?`
      )
    ) {
      return;
    }

    let endpoint;
    if (isDirectSell) {
      endpoint = apiEndpoints.buyDirect;
      console.log("Calling direct buy endpoint");
    } else if (isSellIntent) {
      endpoint = apiEndpoints.acceptAsk;
      console.log("Calling accept asking price endpoint");
    } else {
      alert("This item isn't currently listed for immediate purchase.");
      return;
    }

    callApi(endpoint, "POST", {
      nft_mint: nftId,
    }).then((result) => {
      if (result) {
        alert(`Purchase successful! TX: ${result.transaction_signature}`);
        closeNftModal();

        // Update the card on the grid page to show it's sold
        const purchasedCard = document.querySelector(
          `.nft-card[data-nft-id="${nftId}"]`
        );
        if (purchasedCard) {
          purchasedCard.style.opacity = "0.5";
          purchasedCard.style.pointerEvents = "none"; // Disable further clicks
          const priceElement =
            purchasedCard.querySelector(".relative.mt-2 > p"); // Find price element
          if (priceElement) priceElement.textContent = "Sold";
          const offerButton = purchasedCard.querySelector(".make-offer-link");
          if (offerButton) offerButton.style.display = "none"; // Hide offer button
        }
        // Consider adding a slight delay then maybe refreshing the grid via SSE/fetch
      }
    });
  }

  // --- NFT Detail Modal - Populating (Called after fetching data) ---
  // Make this function globally accessible
  window.populateAndShowNftModal = function (data) {
    if (!nftDetailModal || !data) {
      console.error("Modal element or NFT data missing for population.");
      return;
    }

    const nftId = data.mint_address;

    // Store essential info on the modal element
    nftDetailModal.dataset.currentNftId = nftId;
    nftDetailModal.dataset.isDirectSell = data.has_buy_price ? "true" : "false";
    nftDetailModal.dataset.isSellIntent = data.has_sell_intent
      ? "true"
      : "false";

    // Populate basic info
    nftDetailModal.querySelector("#modal-nft-name").textContent =
      data.name || nftId.slice(0, 16);
    nftDetailModal.querySelector("#modal-nft-image").src =
      data.image_url || "/static/img/nft-default.png";

    // MODIFIED: Use trait_performance_score first, fallback to vitality
    const performanceScore =
      data.trait_performance_score !== null
        ? data.trait_performance_score
        : data.vitality_score;
    const performanceLabelText =
      data.trait_performance_score !== null
        ? "Trait Performance"
        : "Vitality Score";

    nftDetailModal.querySelector("#modal-nft-performance").textContent =
      performanceScore ? `${parseFloat(performanceScore).toFixed(1)}` : "--";
    const performanceLabel = nftDetailModal.querySelector(
      "#modal-nft-performance + span"
    );
    if (performanceLabel) performanceLabel.textContent = performanceLabelText;

    const collectionLink = nftDetailModal.querySelector(
      "#modal-nft-collection-link"
    );
    collectionLink.textContent = data.collection_name || "Collection";
    collectionLink.href = data.collection_address
      ? `/collection/${data.collection_address}/`
      : "#";

    const ownerLink = nftDetailModal.querySelector("#modal-nft-owner-link");
    ownerLink.textContent = data.owner
      ? `${data.owner.slice(0, 4)}...${data.owner.slice(-4)}`
      : "Unknown";
    ownerLink.href = data.owner
      ? `https://solscan.io/account/${data.owner}`
      : "#";

    // Price display and button states
    const priceDisplay = nftDetailModal.querySelector("#modal-nft-price");
    const buyNowBtn = nftDetailModal.querySelector(".bg-primary"); // Adjust selector
    const makeOfferBtn = nftDetailModal.querySelector(".btn-outline"); // Adjust selector

    if (data.has_buy_price && data.buy_price) {
      priceDisplay.textContent = `${parseFloat(data.buy_price).toFixed(2)} SOL`;
      if (buyNowBtn) buyNowBtn.style.display = "inline-flex";
      if (makeOfferBtn) makeOfferBtn.style.display = "inline-flex"; // Or 'none'?
    } else if (data.has_sell_intent && data.asking_price) {
      priceDisplay.textContent = `Ask: ${parseFloat(data.asking_price).toFixed(
        2
      )} SOL`;
      if (buyNowBtn) buyNowBtn.style.display = "inline-flex"; // Button accepts ask
      if (makeOfferBtn) makeOfferBtn.style.display = "inline-flex";
    } else {
      priceDisplay.textContent = "Not Listed";
      if (buyNowBtn) buyNowBtn.style.display = "none";
      if (makeOfferBtn) makeOfferBtn.style.display = "inline-flex";
    }

    // Traits Tab
    const traitsContainer = nftDetailModal.querySelector("#modal-nft-traits");
    traitsContainer.innerHTML =
      data.traits && data.traits.length > 0
        ? data.traits
            .map(
              (
                t
              ) => `<div class="bg-accent-light dark:bg-gray-700/50 p-2 rounded-md">
                      <span class="text-xs text-text-secondary-light">${
                        t.trait_type || t.trait_name || "Trait"
                      }</span>
                      <p class="font-semibold text-text-light dark:text-text-dark">${
                        t.value || t.trait_value || "None"
                      }</p>
                  </div>`
            )
            .join("")
        : '<p class="text-sm text-text-secondary-light">No traits available.</p>';

    // Details Tab
    const onchainContainer = nftDetailModal.querySelector("#modal-nft-onchain");
    const onchainDetails = data.onchain_details || {
      "Token Address": data.mint_address,
      "Collection Address": data.collection_address,
    };
    onchainContainer.innerHTML = Object.entries(onchainDetails)
      .map(
        ([key, value]) => `
            <div class="flex justify-between py-1 border-b border-gray-200 dark:border-border-dark last:border-0">
                <span class="text-text-secondary-light">${key}</span>
                <span class="font-mono text-xs truncate text-right">${
                  value || "--"
                }</span>
            </div>`
      )
      .join("");

    // Memories/Journey Tab
    const memoriesContainer =
      nftDetailModal.querySelector("#modal-nft-journey");
    memoriesContainer.innerHTML =
      data.journey && data.journey.length > 0
        ? data.journey
            .map(
              (event) => `
                  <div class="py-1 border-b border-gray-200 dark:border-border-dark last:border-0">
                        <span class="font-semibold">${
                          event.event_type || "Event"
                        }</span>
                        <span class="text-text-secondary-light text-xs ml-2">${
                          event.amount
                            ? `${parseFloat(event.amount).toFixed(2)} SOL`
                            : ""
                        }</span>
                        <p class="text-xs text-text-secondary-light">
                            ${
                              event.timestamp
                                ? new Date(event.timestamp).toLocaleString()
                                : ""
                            }
                            ${
                              event.buyer
                                ? `| Buyer: ${event.buyer.slice(
                                    0,
                                    4
                                  )}...${event.buyer.slice(-4)}`
                                : ""
                            }
                            ${
                              event.seller
                                ? `| Seller: ${event.seller.slice(
                                    0,
                                    4
                                  )}...${event.seller.slice(-4)}`
                                : ""
                            }
                        </p>
                    </div>
                `
            )
            .join("")
        : '<p class="text-sm text-text-secondary-light">No journey history found.</p>';

    // Reset tabs to default (Traits) and make modal visible
    resetModalTabs();
    nftDetailModal.classList.remove("hidden");

    // Fetch offers (async) - separate call after modal is visible
    fetchAndPopulateOffers(nftId);
  };

  function closeNftModal() {
    if (nftDetailModal) {
      nftDetailModal.classList.add("hidden");
      nftDetailModal.removeAttribute("data-current-nft-id");
      nftDetailModal.removeAttribute("data-is-direct-sell");
      nftDetailModal.removeAttribute("data-is-sell-intent");
    }
  }

  // --- Modal Tab Logic ---
  const modalTabs = nftDetailModal
    ? nftDetailModal.querySelectorAll(".modal-tab")
    : [];
  const modalTabContents = nftDetailModal
    ? nftDetailModal.querySelectorAll(".modal-tab-content")
    : [];

  function resetModalTabs() {
    modalTabs.forEach((t) => {
      const isActive = t.dataset.tab === "traits"; // Default to traits
      t.classList.toggle("border-primary", isActive);
      t.classList.toggle("text-primary", isActive);
      t.classList.toggle("border-transparent", !isActive);
      t.classList.toggle("text-text-secondary-light", !isActive);
    });
    modalTabContents.forEach((c) =>
      c.classList.toggle("hidden", c.id !== "modal-tab-traits")
    );
  }

  modalTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      modalTabs.forEach((t) => {
        t.classList.remove("border-primary", "text-primary");
        t.classList.add("border-transparent", "text-text-secondary-light");
      });
      tab.classList.add("border-primary", "text-primary");
      tab.classList.remove("border-transparent", "text-text-secondary-light");

      const targetId = `modal-tab-${tab.dataset.tab}`;
      modalTabContents.forEach((content) => {
        content.classList.toggle("hidden", content.id !== targetId);
      });
    });
  });

  // --- Fetch Offers (Placeholder) ---
  async function fetchAndPopulateOffers(nftId) {
    const offersContainer = nftDetailModal
      ? nftDetailModal.querySelector("#modal-tab-offers")
      : null;
    if (!offersContainer) return;
    offersContainer.innerHTML =
      '<p class="text-sm text-text-secondary-light">Loading offers...</p>';
    try {
      // Example: const offers = await callApi(`/api/get-nft-offers/${nftId}/`, 'GET');
      // if (offers && offers.length > 0) {
      //     offersContainer.innerHTML = offers.map(offer => `... HTML for offer ...`).join('');
      // } else {
      offersContainer.innerHTML =
        '<p class="text-sm text-text-secondary-light">No active offers found.</p>';
      // }
    } catch (error) {
      console.error("Error fetching offers:", error);
      offersContainer.innerHTML =
        '<p class="text-sm text-red-500">Could not load offers.</p>';
    }
  }
  // Note: Memories/Journey is populated from get_nft_details_api

  // --- Attach Event Listeners ---

  // Modal Buttons (Make Offer & Buy Now inside modal)
  if (nftDetailModal) {
    // Find buttons robustly
    const modalActionButtons = nftDetailModal.querySelector(
      ".bg-accent-light .flex.items-center.gap-2"
    );
    const modalMakeOfferBtn = modalActionButtons
      ? modalActionButtons.querySelector(".btn-outline")
      : null;
    const modalBuyNowBtn = modalActionButtons
      ? modalActionButtons.querySelector(".bg-primary")
      : null;

    if (modalMakeOfferBtn) {
      modalMakeOfferBtn.addEventListener("click", handleMakeOfferClick);
    } else {
      console.warn("Make Offer button inside modal not found.");
    }

    if (modalBuyNowBtn) {
      modalBuyNowBtn.addEventListener("click", handleBuyNowClick);
    } else {
      console.warn("Buy Now button inside modal not found.");
    }

    // Close Button
    if (closeNftModalBtn) {
      closeNftModalBtn.addEventListener("click", closeNftModal);
    }
    // Background Click
    nftDetailModal.addEventListener("click", (e) => {
      if (e.target === nftDetailModal) closeNftModal();
    });
  } else {
    console.warn("NFT Detail Modal element not found.");
  }

  // --- Make Offer Buttons on Grid (Delegation) ---
  // FIXED: This is now un-commented and will work
  if (nftsGridContainer) {
    nftsGridContainer.addEventListener("click", function (event) {
      const makeOfferLink = event.target.closest(".make-note-link");
      const nftCard = event.target.closest(".nft-card");

      if (makeOfferLink) {
        // This is handled by the main listener in collection.html's script
        // to call window.handleMakeOfferClick
        // We'll leave this block empty to avoid double-firing
      } else if (nftCard) {
        // This is handled by the main listener in collection.html's script
        // to call openNftModal
      }
    });
  }
  // The listener in collection_detail.html's <script> block
  // is now the SINGLE source of truth for grid clicks,
  // and it calls the functions (handleMakeOfferClick, openNftModal)
  // that are defined in this file. This is perfect.

  console.log("Marketplace Actions Script Initialized");
}); // End DOMContentLoaded
