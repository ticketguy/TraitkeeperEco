/**
 * Solana Transaction Builder and Signer
 *
 * Handles client-side transaction signing for marketplace operations
 * Requires @solana/web3.js to be loaded
 */

// console.log("solana-transaction.js loaded");

// Check if Solana Web3 is available
if (typeof window.solanaWeb3 === 'undefined') {
    console.error('Solana Web3.js not loaded. Please include it in your HTML.');
}

/**
 * Get the connected wallet provider
 * @returns {Object|null} The wallet provider or null if not connected
 */
function getWalletProvider() {
    // Check for common Solana wallet providers
    if (window.solana && window.solana.isPhantom) {
        return window.solana;
    }
    if (window.solflare && window.solflare.isSolflare) {
        return window.solflare;
    }
    if (window.backpack) {
        return window.backpack;
    }
    if (window.glow) {
        return window.glow;
    }

    console.error('No Solana wallet provider found');
    return null;
}

/**
 * Build a Solana transaction from instruction data returned by backend
 * @param {Object} instructionData - Instruction data from backend
 * @param {string} instructionData.instruction_data - Hex-encoded instruction data
 * @param {Array} instructionData.accounts_meta - Account metadata array
 * @returns {Transaction} Solana transaction object
 */
async function buildTransaction(instructionData) {
    if (!window.solanaWeb3) {
        throw new Error('Solana Web3.js is not loaded');
    }

    const { Transaction, TransactionInstruction, PublicKey } = window.solanaWeb3;

    // Parse instruction data (hex string to buffer)
    const instructionDataBuffer = Buffer.from(instructionData.instruction_data, 'hex');

    // Build account keys from metadata
    const keys = instructionData.accounts_meta.map(account => ({
        pubkey: new PublicKey(account.pubkey),
        isSigner: account.is_signer,
        isWritable: account.is_writable
    }));

    // Get program ID (marketplace program)
    const programId = new PublicKey('tra1TUu99co1Fs7VTnT4GY9ECQcUTKrG2NC5kSHrU5o');

    // Create the instruction
    const instruction = new TransactionInstruction({
        keys: keys,
        programId: programId,
        data: instructionDataBuffer
    });

    // Create transaction and add instruction
    const transaction = new Transaction();
    transaction.add(instruction);

    // Get recent blockhash from RPC
    // Note: You'll need to provide your RPC endpoint
    const connection = new window.solanaWeb3.Connection(
        'https://api.mainnet-beta.solana.com', // Use your RPC URL
        'confirmed'
    );

    const { blockhash } = await connection.getRecentBlockhash();
    transaction.recentBlockhash = blockhash;
    transaction.feePayer = keys[0].pubkey; // First account is typically the fee payer (user)

    return transaction;
}

/**
 * Sign and send a transaction using the connected wallet
 * @param {Transaction} transaction - The transaction to sign
 * @returns {Promise<string>} Transaction signature
 */
async function signAndSendTransaction(transaction) {
    const provider = getWalletProvider();

    if (!provider) {
        throw new Error('No wallet provider found. Please connect your wallet.');
    }

    if (!provider.isConnected) {
        throw new Error('Wallet is not connected. Please connect your wallet first.');
    }

    try {
        // console.log('Requesting wallet to sign transaction...');

        // Different wallets have slightly different APIs
        let signedTransaction;

        if (provider.signAndSendTransaction) {
            // Some wallets (like Phantom) can sign and send in one call
            const { signature } = await provider.signAndSendTransaction(transaction);
            // console.log('Transaction signed and sent. Signature:', signature);
            return signature;
        } else if (provider.signTransaction) {
            // Others require separate sign and send steps
            signedTransaction = await provider.signTransaction(transaction);

            // Send the signed transaction
            const connection = new window.solanaWeb3.Connection(
                'https://api.mainnet-beta.solana.com',
                'confirmed'
            );

            const signature = await connection.sendRawTransaction(signedTransaction.serialize());
            // console.log('Transaction signed and sent. Signature:', signature);

            // Wait for confirmation
            await connection.confirmTransaction(signature);

            return signature;
        } else {
            throw new Error('Wallet does not support transaction signing');
        }
    } catch (error) {
        console.error('Error signing/sending transaction:', error);

        if (error.message && error.message.includes('User rejected')) {
            throw new Error('Transaction was rejected by user');
        }

        throw error;
    }
}

/**
 * Complete marketplace action: 
 * 1. Requests instruction data from the backend (endpoint).
 * 2. Prompts user for signing.
 * 3. Submits the signed transaction to the Solana network.
 * 4. Calls the dedicated confirmation endpoint on the backend.
 * * @param {string} instructionEndpoint - Backend API endpoint to GET Instruction Data (e.g., /api/bid/place/)
 * @param {string} confirmationEndpoint - Backend API endpoint to POST the Signature (e.g., /api/bid/confirm/)
 * @param {Object} actionData - Action data (e.g., nft_mint, amount)
 * @param {string} csrfToken - CSRF token for Django
 * @returns {Promise<Object>} Final result from backend
 */
async function executeMarketplaceAction(instructionEndpoint, confirmationEndpoint, actionData, csrfToken) {
    try {
        // --- Step 1: Request instruction from backend ---
        // console.log('Step 1: Requesting instruction from backend...');

        const step1Response = await fetch(instructionEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(actionData)
        });

        if (!step1Response.ok) {
            const errorData = await step1Response.json();
            throw new Error(errorData.error || `Backend instruction error: ${step1Response.status}`);
        }

        const step1Result = await step1Response.json();

        // Ensure instruction data exists
        if (!step1Result.success || !step1Result.data || !step1Result.data.transaction_instruction) {
             throw new Error(step1Result.data.message || 'Backend failed to return valid instruction data.');
        }

        const instructionData = step1Result.data.transaction_instruction;
        const tempBidId = step1Result.data.temp_bid_id;

        // console.log('Step 2: Building transaction...');
        // --- Step 2: Build and Sign Transaction ---
        const transaction = await buildTransaction(instructionData);

        // console.log('Step 3: Requesting user signature and sending to Solana...');
        // Sign and send transaction to the Solana RPC
        // This function handles waiting for RPC confirmation
        const signature = await signAndSendTransaction(transaction);

        // console.log('Step 4: Confirming transaction with backend...');
        // --- Step 4: Send signature back to the DEDICATED CONFIRMATION endpoint ---
        const finalConfirmationResponse = await fetch(confirmationEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                // Send the transaction signature and the temporary ID created in Step 1
                temp_bid_id: tempBidId,
                transaction_signature: signature,
                ...actionData // Include original data if confirmation needs context
            })
        });

        if (!finalConfirmationResponse.ok) {
            const errorData = await finalConfirmationResponse.json();
            // IMPORTANT: If this step fails, the blockchain transaction succeeded, but the DB update failed.
            throw new Error(`Database finalization error: ${errorData.error || 'Server failed to record sale.'}`);
        }

        const finalResult = await finalConfirmationResponse.json();

        // console.log('Transaction complete and confirmed!', finalResult);
        return finalResult;

    } catch (error) {
        console.error('Marketplace action failed:', error);
        throw error;
    }
}

// Export functions to global scope
window.solanaTransaction = {
    getWalletProvider,
    buildTransaction,
    signAndSendTransaction,
    executeMarketplaceAction
};

// console.log("Solana Transaction utilities initialized");
