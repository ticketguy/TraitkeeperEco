/**
 * Solana Quest Program Utilities
 * Helper functions for interacting with the quest smart contract
 */

// Compute instruction discriminator from method name
// Anchor uses first 8 bytes of SHA256 hash of "global:{method_name}"
async function computeInstructionDiscriminator(methodName) {
    const encoder = new TextEncoder();
    const data = encoder.encode(`global:${methodName}`);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = new Uint8Array(hashBuffer);
    return hashArray.slice(0, 8);
}

// Precomputed discriminators for quest program instructions
const QUEST_INSTRUCTION_DISCRIMINATORS = {
    // These should be computed from your Anchor IDL
    // Format: first 8 bytes of sha256("global:claim_quest_reward")
    claim_quest_reward: new Uint8Array([
        // Placeholder - replace with actual discriminator from IDL
        0xc4, 0x88, 0x5c, 0x55, 0x00, 0x35, 0x86, 0x3f
    ])
};

// Helper to get the discriminator
function getQuestInstructionDiscriminator(methodName) {
    return QUEST_INSTRUCTION_DISCRIMINATORS[methodName] || new Uint8Array(8);
}

// Export for use in quest page
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        computeInstructionDiscriminator,
        getQuestInstructionDiscriminator,
        QUEST_INSTRUCTION_DISCRIMINATORS
    };
}
