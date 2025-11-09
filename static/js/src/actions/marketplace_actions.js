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
  // console.log("Marketplace Actions Script Loaded"); // Debug log

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

    // console.log(
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
        // console.log(`API Response from ${endpoint}:`, result);
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
  //  Attached to window to be globally accessible
  window.handleMakeOfferClick = async function (event) {
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

    // console.log("Make Offer clicked for NFT:", nftId);

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

    try {
      // Check if Solana transaction utilities are available
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log("Using Solana on-chain transaction signing...");

        // Use the new transaction flow
        const result = await window.solanaTransaction.executeMarketplaceAction(
          apiEndpoints.placeBid,
          {
            mint: nftId,
            amount: bidAmount.toString(),
            expiry_hours: 72,
          },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Offer placed successfully! Transaction: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
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
      } else {
        // Fallback to old API call (for testing without Solana Web3)
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi(apiEndpoints.placeBid, "POST", {
          mint: nftId,
          amount: bidAmount.toString(),
          expiry_hours: 72,
        });

        if (result) {
          alert(
            `Offer placed successfully! Bid ID: ${result.bid_id.slice(
              0,
              12
            )}...`
          );
          if (
            nftDetailModal &&
            !nftDetailModal.classList.contains("hidden") &&
            nftDetailModal.dataset.currentNftId === nftId
          ) {
            fetchAndPopulateOffers(nftId);
          }
        }
      }
    } catch (error) {
      console.error("Error placing offer:", error);
      alert(`Failed to place offer: ${error.message}`);
    }
  };

  // --- "Buy Now" Logic ---
  async function handleBuyNowClick(event) {
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
      // console.log("Calling direct buy endpoint");
    } else if (isSellIntent) {
      endpoint = apiEndpoints.acceptAsk;
      // console.log("Calling accept asking price endpoint");
    } else {
      alert("This item isn't currently listed for immediate purchase.");
      return;
    }

    try {
      // Check if Solana transaction utilities are available
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing for purchase..."
        );

        // Use the new transaction flow
        const result = await window.solanaTransaction.executeMarketplaceAction(
          endpoint,
          {
            mint: nftId,
          },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Purchase successful! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          closeNftModal();

          // Update the card on the grid page to show it's sold
          const purchasedCard = document.querySelector(
            `.nft-card[data-nft-id="${nftId}"]`
          );
          if (purchasedCard) {
            purchasedCard.style.opacity = "0.5";
            purchasedCard.style.pointerEvents = "none";
            const priceElement =
              purchasedCard.querySelector(".relative.mt-2 > p");
            if (priceElement) priceElement.textContent = "Sold";
            const offerButton = purchasedCard.querySelector(".make-offer-link");
            if (offerButton) offerButton.style.display = "none";
          }
        }
      } else {
        // Fallback to old API call (for testing without Solana Web3)
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi(endpoint, "POST", {
          mint: nftId,
        });

        if (result) {
          alert(`Purchase successful! TX: ${result.transaction_signature}`);
          closeNftModal();

          const purchasedCard = document.querySelector(
            `.nft-card[data-nft-id="${nftId}"]`
          );
          if (purchasedCard) {
            purchasedCard.style.opacity = "0.5";
            purchasedCard.style.pointerEvents = "none";
            const priceElement =
              purchasedCard.querySelector(".relative.mt-2 > p");
            if (priceElement) priceElement.textContent = "Sold";
            const offerButton = purchasedCard.querySelector(".make-offer-link");
            if (offerButton) offerButton.style.display = "none";
          }
        }
      }
    } catch (error) {
      console.error("Error completing purchase:", error);
      alert(`Failed to complete purchase: ${error.message}`);
    }
  }

  // --- NFT Detail Modal - Populating (Called after fetching data) ---
  // Make this function globally accessible
  window.populateAndShowNftModal = function (data) {
    if (!nftDetailModal || !data) {
      console.error("Modal element or NFT data missing for population.");
      return;
    }

    const nftId = data.mint_address;

    // Store NFT mint globally for auction modal
    window.currentNFTMint = nftId;

    // Store essential info on the modal element
    nftDetailModal.dataset.currentNftId = nftId;
    nftDetailModal.dataset.isDirectSell = data.has_buy_price ? "true" : "false";
    nftDetailModal.dataset.isSellIntent = data.has_sell_intent
      ? "true"
      : "false";
    nftDetailModal.dataset.isOwner = data.is_owner ? "true" : "false";

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

    // Price display and dynamic button states
    const priceDisplay = nftDetailModal.querySelector("#modal-nft-price");

    // Get dynamic action containers
    const buyerActions = nftDetailModal.querySelector("#buyer-actions");
    const ownerActions = nftDetailModal.querySelector("#owner-actions");
    const buyNowBtn = nftDetailModal.querySelector("#buy-now-btn");
    const listForSaleForm = nftDetailModal.querySelector("#list-for-sale-form");
    const alreadyListedMsg = nftDetailModal.querySelector(
      "#already-listed-msg"
    );
    const manageOffersBtn = nftDetailModal.querySelector("#manage-offers-btn");
    const createAuctionBtn = nftDetailModal.querySelector("#create-auction-btn");

    const isOwner = data.is_owner || false;
    const isListed = data.has_sell_intent || data.has_buy_price;
    const hasActiveAuction = data.has_active_auction || false;

    if (isOwner) {
      // Show owner actions
      if (buyerActions) buyerActions.style.display = "none";
      if (ownerActions) ownerActions.style.display = "block";

      // Show list form or "already listed" message
      if (isListed) {
        if (listForSaleForm) listForSaleForm.style.display = "none";
        if (alreadyListedMsg) alreadyListedMsg.style.display = "block";
      } else {
        if (listForSaleForm) listForSaleForm.style.display = "flex";
        if (alreadyListedMsg) alreadyListedMsg.style.display = "none";
      }

      // Show manage offers button
      if (manageOffersBtn) manageOffersBtn.style.display = "inline-flex";

      // Show create auction button only if NFT is not listed and not in active auction
      if (createAuctionBtn) {
        createAuctionBtn.style.display = (!isListed && !hasActiveAuction) ? "inline-flex" : "none";
      }
    } else {
      // Show buyer actions
      if (buyerActions) buyerActions.style.display = "block";
      if (ownerActions) ownerActions.style.display = "none";

      // Show buy now button only if listed
      if (buyNowBtn) {
        buyNowBtn.style.display = isListed ? "inline-flex" : "none";
      }
    }

    // Update price display
    if (data.has_buy_price && data.buy_price) {
      priceDisplay.textContent = `${parseFloat(data.buy_price).toFixed(2)} SOL`;
    } else if (data.has_sell_intent && data.asking_price) {
      priceDisplay.textContent = `Ask: ${parseFloat(data.asking_price).toFixed(
        2
      )} SOL`;
    } else {
      priceDisplay.textContent = "Not Listed";
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

  // --- Fetch Offers ---
  async function fetchAndPopulateOffers(nftId) {
    const offersEmptyDiv = nftDetailModal
      ? nftDetailModal.querySelector("#modal-offers-empty")
      : null;
    const offersListDiv = nftDetailModal
      ? nftDetailModal.querySelector("#modal-offers-list")
      : null;

    if (!offersEmptyDiv || !offersListDiv) return;

    // Show loading state
    offersEmptyDiv.style.display = "block";
    offersEmptyDiv.textContent = "Loading offers...";
    offersListDiv.style.display = "none";

    try {
      // Fetch offers from backend
      const offers = await callApi(
        `/marketplace/api/get-nft-offers/${nftId}/`,
        "GET"
      );

      if (offers && offers.length > 0) {
        // Hide empty message, show list
        offersEmptyDiv.style.display = "none";
        offersListDiv.style.display = "block";

        // Check if current user is the NFT owner
        const currentNftData = nftDetailModal.dataset;
        const isOwner = currentNftData.isOwner === "true";

        // Populate offers list with Accept/Reject buttons for owner
        offersListDiv.innerHTML = offers
          .map((offer) => {
            const bidderShort = `${offer.bidder.slice(
              0,
              4
            )}...${offer.bidder.slice(-4)}`;
            const createdAt = offer.created_at
              ? new Date(offer.created_at).toLocaleString()
              : "Unknown date";
            const expiresAt = offer.expires_at
              ? new Date(offer.expires_at).toLocaleString()
              : "No expiry";

            let actionButtons = "";
            if (isOwner && offer.status === "PENDING") {
              actionButtons = `
              <div class="flex gap-2 mt-2">
                <button
                  onclick="window.handleAcceptBidClick('${offer.bid_id}')"
                  class="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-xs rounded"
                >
                  Accept
                </button>
                <button
                  onclick="window.handleCounterOffer('${offer.bid_id}')"
                  class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded"
                >
                  Counter
                </button>
                <button
                  onclick="window.handleRejectBidClick('${offer.bid_id}')"
                  class="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded"
                >
                  Reject
                </button>
              </div>
            `;
            } else if (!isOwner && offer.status === "PENDING") {
              // Show cancel button for bidder's own bids
              actionButtons = `
              <div class="flex gap-2 mt-2">
                <button
                  onclick="window.handleCancelBidClick('${offer.bid_id}')"
                  class="px-3 py-1 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded"
                >
                  Cancel
                </button>
              </div>
            `;
            }

            return `
            <div class="bg-accent-light dark:bg-gray-700/50 p-3 rounded-lg">
              <div class="flex justify-between items-start">
                <div>
                  <p class="font-semibold text-text-light dark:text-text-dark">
                    ${parseFloat(offer.amount).toFixed(2)} SOL
                  </p>
                  <p class="text-xs text-text-secondary-light dark:text-text-secondary-dark">
                    From: ${bidderShort}
                  </p>
                  <p class="text-xs text-text-secondary-light dark:text-text-secondary-dark">
                    Created: ${createdAt}
                  </p>
                  <p class="text-xs text-text-secondary-light dark:text-text-secondary-dark">
                    Expires: ${expiresAt}
                  </p>
                </div>
                <span class="px-2 py-1 text-xs rounded ${
                  offer.status === "PENDING"
                    ? "bg-yellow-100 text-yellow-800"
                    : offer.status === "ACCEPTED"
                    ? "bg-green-100 text-green-800"
                    : offer.status === "REJECTED"
                    ? "bg-red-100 text-red-800"
                    : "bg-gray-100 text-gray-800"
                }">
                  ${offer.status}
                </span>
              </div>
              ${actionButtons}
            </div>
          `;
          })
          .join("");
      } else {
        // No offers found
        offersEmptyDiv.style.display = "block";
        offersEmptyDiv.textContent = "No active offers found.";
        offersListDiv.style.display = "none";
      }
    } catch (error) {
      console.error("Error fetching offers:", error);
      offersEmptyDiv.style.display = "block";
      offersEmptyDiv.textContent = "Could not load offers.";
      offersEmptyDiv.classList.add("text-red-500");
      offersListDiv.style.display = "none";
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

  // --- Accept Bid Logic ---
  window.handleAcceptBidClick = async function (bidId) {
    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to accept bids.");
      return;
    }

    if (
      !confirm(`Accept this bid? The NFT will be transferred to the buyer.`)
    ) {
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing to accept bid..."
        );

        const result = await window.solanaTransaction.executeMarketplaceAction(
          apiEndpoints.acceptBid,
          { bid_id: bidId },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Bid accepted! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          // Refresh page or update UI
          window.location.reload();
        }
      } else {
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi(apiEndpoints.acceptBid, "POST", {
          bid_id: bidId,
        });
        if (result) {
          alert(`Bid accepted! TX: ${result.transaction_signature}`);
          window.location.reload();
        }
      }
    } catch (error) {
      console.error("Error accepting bid:", error);
      alert(`Failed to accept bid: ${error.message}`);
    }
  };

  // --- Reject Bid Logic ---
  window.handleRejectBidClick = async function (bidId) {
    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to reject bids.");
      return;
    }

    if (!confirm(`Reject this bid? Bidder will be notified.`)) {
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing to reject bid..."
        );

        const result = await window.solanaTransaction.executeMarketplaceAction(
          apiEndpoints.rejectBid,
          { bid_id: bidId },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Bid rejected! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          window.location.reload();
        }
      } else {
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi(apiEndpoints.rejectBid, "POST", {
          bid_id: bidId,
        });
        if (result) {
          alert(`Bid rejected! TX: ${result.transaction_signature}`);
          window.location.reload();
        }
      }
    } catch (error) {
      console.error("Error rejecting bid:", error);
      alert(`Failed to reject bid: ${error.message}`);
    }
  };

  // --- Cancel Bid Logic ---
  window.handleCancelBidClick = async function (bidId) {
    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to cancel bids.");
      return;
    }

    if (!confirm(`Cancel your bid? Your funds will be returned.`)) {
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing to cancel bid..."
        );

        const result = await window.solanaTransaction.executeMarketplaceAction(
          apiEndpoints.cancelBid,
          { bid_id: bidId },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Bid cancelled! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          window.location.reload();
        }
      } else {
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi(apiEndpoints.cancelBid, "POST", {
          bid_id: bidId,
        });
        if (result) {
          alert(`Bid cancelled! TX: ${result.transaction_signature}`);
          window.location.reload();
        }
      }
    } catch (error) {
      console.error("Error cancelling bid:", error);
      alert(`Failed to cancel bid: ${error.message}`);
    }
  };

  // --- Set Sell Intent Logic (Modified to handle form input) ---
  window.handleSetSellIntentClick = async function (nftMint, askingPrice) {
    const config = window.traitkeeperConfig || {};
    const apiEndpoints = config.apiEndpoints || {};
    const csrfToken = config.csrfToken;
    const isAuthenticated = config.isAuthenticated || false;

    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to list NFTs.");
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing to set sell intent..."
        );

        // NOTE: The backend service handles both direct-sell and sell-intent logic
        // based on the context. We assume this button is for Sell Intent (negotiable).
        const result = await window.solanaTransaction.executeMarketplaceAction(
          apiEndpoints.setSellIntent, // Calls '/api/sell-intent/set/'
          {
            mint: nftMint,
            asking_price: askingPrice.toString(),
          },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `NFT listed! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          window.location.reload();
        }
      } else {
        // Fallback implementation removed for brevity, assume Solana is required
        alert("Solana transaction utilities not available. Cannot list NFT.");
      }
    } catch (error) {
      console.error("Error setting sell intent:", error);
      alert(`Failed to list NFT: ${error.message}`);
    }
  };

  // --- Helper: Handle List for Sale Form Submission ---
  window.handleListForSale = async function () {
    const nftModal = document.getElementById("nft-detail-modal");
    const priceInput = document.getElementById("modal-asking-price-input");
    // Assume a checkbox for direct sell vs. sell intent exists if needed later

    if (!nftModal || !priceInput) {
      alert("Cannot find list for sale form elements.");
      return;
    }

    const nftMint = nftModal.dataset.currentNftId;
    const askingPrice = parseFloat(priceInput.value);

    if (!nftMint) {
      alert("Cannot determine NFT to list.");
      return;
    }

    if (isNaN(askingPrice) || askingPrice <= 0) {
      alert("Please enter a valid price in SOL.");
      return;
    }

    // --- Call the correct set_sell_intent handler ---
    await window.handleSetSellIntentClick(nftMint, askingPrice);
  };

  // --- Helper: Show Offers Tab ---
  window.showOffersTab = function () {
    const nftModal = document.getElementById("nft-detail-modal");
    if (!nftModal) return;

    // Find the offers tab button and click it
    const offersTabBtn = Array.from(
      nftModal.querySelectorAll(".modal-tab")
    ).find((tab) => tab.dataset.tab === "offers");

    if (offersTabBtn) {
      offersTabBtn.click();
    }
  };


  window.handleCreateAuction = async function (
    nftMint,
    startingPrice,
    duration,
    reservePrice
  ) {
    const config = window.traitkeeperConfig || {};
    const csrfToken = config.csrfToken;

    const result = await window.solanaTransaction.executeMarketplaceAction(
      "/marketplace/api/auction/create/", // Direct endpoint from your urls.py
      {
        nft_mint: nftMint,
        starting_price: startingPrice,
        duration_hours: duration,
        reserve_price: reservePrice,
      },
      csrfToken
    );
    if (result && result.success) {
      alert(
        `Auction created! TX: ${result.data.transaction_signature.slice(
          0,
          12
        )}...`
      );
      window.location.reload();
    }
  };

  // Place Auction Bid
  window.handlePlaceAuctionBid = async function (auctionId, amount) {
    const config = window.traitkeeperConfig || {};
    const csrfToken = config.csrfToken;

    const result = await window.solanaTransaction.executeMarketplaceAction(
      "/marketplace/api/auction/bid/",
      {
        auction_id: auctionId,
        amount: amount,
      },
      csrfToken
    );
    if (result && result.success) {
      alert(
        `Auction bid placed! TX: ${result.data.transaction_signature.slice(
          0,
          12
        )}...`
      );
      window.location.reload();
    }
  };

  // Cancel Auction
  window.handleCancelAuction = async function (auctionId) {
    const config = window.traitkeeperConfig || {};
    const csrfToken = config.csrfToken;
    const isAuthenticated = config.isAuthenticated || false;

    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to cancel auctions.");
      return;
    }

    if (
      !confirm(
        "Cancel this auction? This can only be done if no bids have been placed."
      )
    ) {
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing to cancel auction..."
        );

        const result = await window.solanaTransaction.executeMarketplaceAction(
          "/marketplace/api/auction/cancel/",
          { auction_id: auctionId },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Auction cancelled! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          window.location.reload();
        }
      } else {
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi("/marketplace/api/auction/cancel/", "POST", {
          auction_id: auctionId,
        });
        if (result) {
          alert(`Auction cancelled! TX: ${result.transaction_signature}`);
          window.location.reload();
        }
      }
    } catch (error) {
      console.error("Error cancelling auction:", error);
      alert(`Failed to cancel auction: ${error.message}`);
    }
  };

  // Finalize Auction
  window.handleFinalizeAuction = async function (auctionId) {
    const config = window.traitkeeperConfig || {};
    const csrfToken = config.csrfToken;

    if (
      !confirm(
        "Confirm auction finalization? Funds and NFT will be transferred."
      )
    )
      return;

    const result = await window.solanaTransaction.executeMarketplaceAction(
      "/marketplace/api/auction/finalize/",
      { auction_id: auctionId },
      csrfToken
    );
    if (result && result.success) {
      alert(
        `Auction finalized! Winner: ${result.data.winner.slice(
          0,
          8
        )}... Price: ${result.data.final_price} SOL.`
      );
      window.location.reload();
    }
  };

  // --- Counter Offer Logic ---
  window.handleCounterOffer = async function (bidId) {
    const config = window.traitkeeperConfig || {};
    const csrfToken = config.csrfToken;
    const isAuthenticated = config.isAuthenticated || false;

    if (!isAuthenticated) {
      alert("Please log in or connect your wallet to counter offers.");
      return;
    }

    // Prompt for counter amount
    const counterAmountStr = prompt("Enter your counter-offer amount in SOL:");
    if (counterAmountStr === null) return; // User cancelled

    const counterAmount = parseFloat(counterAmountStr);
    if (isNaN(counterAmount) || counterAmount <= 0) {
      alert("Invalid counter amount. Please enter a positive number.");
      return;
    }

    if (
      !confirm(
        `Counter this bid with ${counterAmount} SOL? This will reject the original bid and set a new asking price.`
      )
    ) {
      return;
    }

    try {
      if (typeof window.solanaTransaction !== "undefined") {
        // console.log(
          "Using Solana on-chain transaction signing for counter-offer..."
        );

        const result = await window.solanaTransaction.executeMarketplaceAction(
          "/marketplace/api/bid/counter/",
          {
            bid_id: bidId,
            counter_amount: counterAmount.toString(),
          },
          csrfToken
        );

        if (result && result.success) {
          alert(
            `Counter-offer sent! TX: ${result.data.transaction_signature.slice(
              0,
              12
            )}...`
          );
          window.location.reload();
        }
      } else {
        console.warn(
          "Solana transaction utilities not loaded. Using fallback API call."
        );
        const result = await callApi("/marketplace/api/bid/counter/", "POST", {
          bid_id: bidId,
          counter_amount: counterAmount.toString(),
        });
        if (result) {
          alert(`Counter-offer sent! TX: ${result.transaction_signature}`);
          window.location.reload();
        }
      }
    } catch (error) {
      console.error("Error sending counter-offer:", error);
      alert(`Failed to send counter-offer: ${error.message}`);
    }
  };

  // console.log("Marketplace Actions Script Initialized");
}); // End DOMContentLoaded
