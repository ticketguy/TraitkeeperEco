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
// Computed using SHA256("global:{method_name}")
const QUEST_INSTRUCTION_DISCRIMINATORS = {
    // claim_quest_reward: sha256("global:claim_quest_reward")[0:8]
    claim_quest_reward: new Uint8Array([
        0x49, 0x7b, 0xbf, 0xce, 0x3f, 0x7f, 0xf7, 0x0c
    ]),

    // update_quest_progress: sha256("global:update_quest_progress")[0:8]
    update_quest_progress: new Uint8Array([
        0xa7, 0xcc, 0x50, 0xc8, 0x89, 0x3e, 0x3f, 0xcf
    ]),

    // initialize_quest_user: sha256("global:initialize_quest_user")[0:8]
    initialize_quest_user: new Uint8Array([
        0xa0, 0x7d, 0x4a, 0xd0, 0x1d, 0x34, 0x89, 0x1f
    ]),

    // create_quest: sha256("global:create_quest")[0:8]
    create_quest: new Uint8Array([
        0x70, 0x31, 0x20, 0xe0, 0xff, 0xad, 0x05, 0x07
    ])
};

// Helper to get the discriminator
function getQuestInstructionDiscriminator(methodName) {
    const discriminator = QUEST_INSTRUCTION_DISCRIMINATORS[methodName];

    if (!discriminator) {
        throw new Error(`Unknown quest instruction: ${methodName}. Available: ${Object.keys(QUEST_INSTRUCTION_DISCRIMINATORS).join(', ')}`);
    }

    // Safety check: ensure discriminator is not all zeros (placeholder)
    const isZeroFilled = discriminator.every(byte => byte === 0);
    if (isZeroFilled) {
        throw new Error(`Instruction discriminator for "${methodName}" is not initialized! This is a critical error.`);
    }

    return discriminator;
}

// Export for use in quest page
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        computeInstructionDiscriminator,
        getQuestInstructionDiscriminator,
        QUEST_INSTRUCTION_DISCRIMINATORS
    };
}
