/**
 * Verification script for quest instruction discriminators
 * Run in browser console or Node.js to verify correctness
 */

// Test the discriminator computation
async function verifyDiscriminators() {
    console.log('🔍 Verifying Quest Instruction Discriminators...\n');

    const expectedDiscriminators = {
        claim_quest_reward: [0x49, 0x7b, 0xbf, 0xce, 0x3f, 0x7f, 0xf7, 0x0c],
        update_quest_progress: [0xa7, 0xcc, 0x50, 0xc8, 0x89, 0x3e, 0x3f, 0xcf],
        initialize_quest_user: [0xa0, 0x7d, 0x4a, 0xd0, 0x1d, 0x34, 0x89, 0x1f],
        create_quest: [0x70, 0x31, 0x20, 0xe0, 0xff, 0xad, 0x05, 0x07]
    };

    let allPassed = true;

    for (const [method, expected] of Object.entries(expectedDiscriminators)) {
        const input = `global:${method}`;
        const encoder = new TextEncoder();
        const data = encoder.encode(input);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const computed = new Uint8Array(hashBuffer).slice(0, 8);

        const matches = computed.every((byte, i) => byte === expected[i]);

        if (matches) {
            console.log(`✅ ${method}: VALID`);
            console.log(`   Hex: ${Array.from(computed).map(b => b.toString(16).padStart(2, '0')).join('')}`);
        } else {
            console.log(`❌ ${method}: MISMATCH`);
            console.log(`   Expected: [${expected.map(b => '0x' + b.toString(16).padStart(2, '0')).join(', ')}]`);
            console.log(`   Computed: [${Array.from(computed).map(b => '0x' + b.toString(16).padStart(2, '0')).join(', ')}]`);
            allPassed = false;
        }
    }

    console.log('\n' + '='.repeat(50));
    if (allPassed) {
        console.log('✅ ALL DISCRIMINATORS VERIFIED - PRODUCTION READY');
    } else {
        console.log('❌ VERIFICATION FAILED - DO NOT USE IN PRODUCTION');
    }
    console.log('='.repeat(50));

    return allPassed;
}

// Auto-run if in browser
if (typeof window !== 'undefined') {
    verifyDiscriminators();
}

// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { verifyDiscriminators };
}
