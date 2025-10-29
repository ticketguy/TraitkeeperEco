from typing import List, Dict, Optional, Any

from borsh_construct import CStruct, U8, U16, U32, U64, I16, I64, String, Vec, Option, Bytes
from solders.pubkey import Pubkey
from construct import Bytes as ConstructBytes 


# =============================================================================
# MARKETPLACE PROGRAM IDs (Unchanged, assuming correct)
# =============================================================================
MARKETPLACE_PROGRAMS = {
    # Magic Eden
    'magic_eden_v2': 'M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K',
    'magic_eden_mmm': 'mmm3XBJg5gk8XJxEKBvdgptZz6SgK4tXvn36sodowMc',

    # Tensor Suite
    'tensor_cnft_marketplace': 'TCMPhJdwDryooaGtiocG1u3xcYbRpiJzb283XfCZsDp',  # TComp
    'tensor_amm': 'TAMM6ub33ij1mbetoMyVBLeKY5iP41i4UPUJQGkhfsg',
    'tensor_escrow': 'TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN',  # TensorSwap

    # Other Marketplaces
    'opensea': '3o9d13qUvEuuauhFrVom1vuCzgNsJifeaBYDPquaT73Y',
    'haus': 'hausS13jsjafwWwGqZTUQRmWyvyxn9EQpqMwV1PBBmk',
}

# =============================================================================
# UPDATED DISCRIMINATORS FROM IDLs (Sighashes)
# =============================================================================

# Magic Eden V2 (from magic eden v2.json)
ME_V2_IX_BUY = bytes.fromhex("4d8d1340beae1206")  # buyV2
ME_V2_IX_EXECUTE_SALE = bytes.fromhex("80845dc2cd0368dc")  # executeSaleV2
ME_V2_IX_SELL = bytes.fromhex("33e685a4017f83ad")  # sell
ME_V2_IX_CANCEL_SELL = bytes.fromhex("7a9ba994d6df4168")  # cancelSell
ME_V2_IX_DEPOSIT = bytes.fromhex("f223c68952e1f2b6")  # deposit
ME_V2_IX_WITHDRAW = bytes.fromhex("b712469c946da122")  # withdraw

# Backward compatibility
ME_IX_BUY_V2 = ME_V2_IX_BUY
ME_IX_EXECUTE_SALE_V2 = ME_V2_IX_EXECUTE_SALE
ME_IX_LIST = ME_V2_IX_SELL
ME_IX_DELIST = ME_V2_IX_CANCEL_SELL
ME_IX_WITHDRAW = ME_V2_IX_WITHDRAW

# Legacy (add if needed, but update with new)
ME_IX_BID = bytes.fromhex("189f6234ab528fa1")
ME_IX_BID_CANCEL = bytes.fromhex("7ad46e8c921f583d")

# Magic Eden MMM (from magic eden mm.json)
ME_MMM_IX_CREATE_POOL = bytes.fromhex("f4ec750412003e58")  # createPool
ME_MMM_IX_UPDATE_POOL = bytes.fromhex("55317abc354db884")  # updatePool
ME_MMM_IX_SOL_FULFILL_BUY = bytes.fromhex("97de2e3741a76cb1")  # solFulfillBuy
ME_MMM_IX_SOL_FULFILL_SELL = bytes.fromhex("45295bc43e5e43a1")  # solFulfillSell
ME_MMM_IX_DEPOSIT_SELL = bytes.fromhex("78a032b0510444bb")  # depositSell
ME_MMM_IX_WITHDRAW_SELL = bytes.fromhex("7ef36c038082e10d")  # withdrawSell

# Tensor cNFT Marketplace (TComp from tcomp.json)
TCOMP_IX_LIST = bytes.fromhex("36aec14311298426")  # list
TCOMP_IX_DELIST = bytes.fromhex("3788cd6b6bad041f")  # delist
TCOMP_IX_BUY = bytes.fromhex("66063d1201daebea")  # buy
TCOMP_IX_BUY_SPL = bytes.fromhex("92ccca556152abae")  # buySpl
TCOMP_IX_BID = bytes.fromhex("c738552692f3259e")  # bid
TCOMP_IX_CANCEL_BID = bytes.fromhex("6a8e437cae6a0c7d")  # cancelBid
TCOMP_IX_TAKE_BID = bytes.fromhex("b5c80a5f0eb09040")  # takeBid
TCOMP_IX_TAKE_BID_SPL = bytes.fromhex("b887b7cc87d4259e")  # takeBidSpl
TCOMP_IX_EDIT = bytes.fromhex("0fb72156571c9791")  # edit


# Tensor AMM (from tensor amm_program.json)
TENSOR_AMM_IX_CREATE_POOL = bytes.fromhex("f4ec750412003e58")  # createPool
TENSOR_AMM_IX_EDIT_POOL = bytes.fromhex("01f7e968652bbed2")  # editPool
TENSOR_AMM_IX_CLOSE_POOL = bytes.fromhex("4efda51b9fb91dec")  # closePool
TENSOR_AMM_IX_DEPOSIT_SOL = bytes.fromhex("ea2547ee8871ffc4")  # depositSol
TENSOR_AMM_IX_WITHDRAW_SOL = bytes.fromhex("741ce3650e1880a0")  # withdrawSol
TENSOR_AMM_IX_BUY_NFT = bytes.fromhex("4f7a05d6b38a2a5c")  # buyNft
TENSOR_AMM_IX_SELL_NFT_TOKEN_POOL = bytes.fromhex("0393ff7d1fdd79b6")  # sellNftTokenPool
TENSOR_AMM_IX_SELL_NFT_TRADE_POOL = bytes.fromhex("eb571e720e6b2148")  # sellNftTradePool

# Tensor Escrow (TensorSwap from tensorswap.json)
TSWAP_IX_INIT_POOL = bytes.fromhex("0281985edd28635e")  # initPool
TSWAP_IX_CLOSE_POOL = bytes.fromhex("4efda51b9fb91dec")  # closePool
TSWAP_IX_DEPOSIT_SOL = bytes.fromhex("dac2ba41884d4cb7")  # depositNft (wait, mismatch? Wait, depositNft is for NFT, but depositSol not listed; adjust based on IDL)
# Note: tensorswap.json has depositNft: dac2ba41884d4cb7, withdrawNftSol: 87e14d5a30da1fd4, etc.
TSWAP_IX_DEPOSIT_NFT = bytes.fromhex("dac2ba41884d4cb7")  # depositNft
TSWAP_IX_WITHDRAW_NFT_SOL = bytes.fromhex("87e14d5a30da1fd4")  # withdrawNftSol
TSWAP_IX_WITHDRAW_NFT_TRADE = bytes.fromhex("e11ab4fea76c511f")  # withdrawNftTrade
TSWAP_IX_BUY_NFT = bytes.fromhex("4f7a05d6b38a2a5c")  # buyNft
TSWAP_IX_SELL_NFT_TOKEN_POOL = bytes.fromhex("0393ff7d1fdd79b6")  # sellNftTokenPool
TSWAP_IX_SELL_NFT_TRADE_POOL = bytes.fromhex("eb571e720e6b2148")  # sellNftTradePool
TSWAP_IX_EDIT_POOL = bytes.fromhex("01f7e968652bbed2")  # editPool
TSWAP_IX_TAKE_BID = bytes.fromhex("b5c80a5f0eb09040")  # takeBid
TSWAP_IX_WITHDRAW_FEES = bytes.fromhex("bfff45a379070fe2")  # withdrawFees
TSWAP_IX_WITHDRAW_MM_FEES = bytes.fromhex("c4980c417a5b7c14")  # withdrawMmFees

# Haus (from haus auction_house.json)
HAUS_IX_WITHDRAW_FROM_FEE = bytes.fromhex("f92220cd99c1ace5")  # withdrawFromFee
HAUS_IX_WITHDRAW_FROM_TREASURY = bytes.fromhex("4aaf7c8f2b37f9fc")  # withdrawFromTreasury
HAUS_IX_UPDATE_AUCTION_HOUSE = bytes.fromhex("bd6750836c37144c")  # updateAuctionHouse
HAUS_IX_CREATE_AUCTION_HOUSE = bytes.fromhex("67ed663e71e9b980")  # createAuctionHouse
HAUS_IX_BUY = bytes.fromhex("66063d1201daebea")  # buy
HAUS_IX_SELL = bytes.fromhex("33e685a4017f83ad")  # sell
HAUS_IX_EXECUTE_SALE = bytes.fromhex("872433ebac772bb9")  # executeSale
HAUS_IX_CANCEL = bytes.fromhex("e8dbdf29dbecdcbe")  # cancel

# OpenSea (assuming similar; update if IDL available)
OPENSEA_IX_SELL = bytes.fromhex("33e685a4017f83ad")  # Placeholder, compute if needed
OPENSEA_IX_BUY = bytes.fromhex("66063d1201daebea")
OPENSEA_IX_LIST = bytes.fromhex("36aec14311298426")
OPENSEA_IX_DELIST = bytes.fromhex("3788cd6b6bad041f")

# Layout structures (update based on IDLs; examples)
ME_V2_EXECUTE_SALE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "escrow_payment_bump" / U8,
    "program_as_signer_bump" / U8,
    "buyer_price" / U64,
    "token_size" / U64,
    "buyer_state_expiry" / I64,
    "seller_state_expiry" / I64,
    "maker_fee_bp" / I16,
    "taker_fee_bp" / U16
)

MIP1_SELL_ARGS = CStruct(
    "price" / U64,
    "expiry" / I64
)

ME_V2_MIP1_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / MIP1_SELL_ARGS
)
ME_V2_CANCEL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "buyer_price" / U64,
    "token_size" / U64,
    "seller_state_expiry" / I64
)

CORE_SELL_ARGS = CStruct(
    "price" / U64,
    "expiry" / I64,
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_V2_CORE_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / CORE_SELL_ARGS
)
ME_V2_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "buyer_price" / U64,
    "token_size" / U64,
    "buyer_state_expiry" / I64,
    "buyer_creator_royalty_bp" / U16,
    "extra_args" / Vec(U8)
)

ME_V2_MIP1_CANCEL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8)
)

CORE_CANCEL_SELL_ARGS = CStruct(
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_V2_CORE_CANCEL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / CORE_CANCEL_SELL_ARGS
)

CORE_EXECUTE_SALE_V2_ARGS = CStruct(
    "price" / U64,
    "maker_fee_bp" / U16,
    "taker_fee_bp" / U16,
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_V2_CORE_EXECUTE_SALE_V2_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / CORE_EXECUTE_SALE_V2_ARGS
)

ME_V2_DEPOSIT_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "escrow_payment_bump" / U8,
    "amount" / U64
)

ME_V2_WITHDRAW_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "escrow_payment_bump" / U8,
    "amount" / U64
)

ME_V2_UPDATE_AUCTION_HOUSE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "seller_fee_basis_points" / Option(U16),
    "buyer_referral_bp" / Option(U16),
    "seller_referral_bp" / Option(U16),
    "requires_notary" / Option(U8),
    "nprob" / Option(U8)
)

SOL_MIP1_FULFILL_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "max_payment_amount" / U64,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_MIP1_FULFILL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_MIP1_FULFILL_SELL_ARGS
)

SOL_EXT_FULFILL_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "max_payment_amount" / U64,
    "buyside_creator_royalty_bp" / U16,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_EXT_FULFILL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_EXT_FULFILL_SELL_ARGS
)

MIP1_WITHDRAW_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "allowlist_aux" / Option(String)
)

# Define the full instruction layout
ME_MMM_MIP1_WITHDRAW_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / MIP1_WITHDRAW_SELL_ARGS
)

MPL_CORE_WITHDRAW_SELL_ARGS = CStruct(
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_MMM_MPL_CORE_WITHDRAW_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / MPL_CORE_WITHDRAW_SELL_ARGS
)


SOL_MPL_CORE_FULFILL_SELL_ARGS = CStruct(
    "max_payment_amount" / U64,
    "buyside_creator_royalty_bp" / U16,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16,
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_MMM_SOL_MPL_CORE_FULFILL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_MPL_CORE_FULFILL_SELL_ARGS
)

SOL_WITHDRAW_BUY_ARGS = CStruct(
    "payment_amount" / U64
)

# Define the full instruction layout
ME_MMM_SOL_WITHDRAW_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_WITHDRAW_BUY_ARGS
)

# The metadataArgs field is complex; representing it as raw ConstructBytes  is the most robust approach.
SOL_CNFT_FULFILL_BUY_ARGS = CStruct(
    "asset_id" / ConstructBytes (32),
    "root" / ConstructBytes (32),
    "nonce" / U64,
    "index" / U32,
    "min_payment_amount" / U64,
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16,
    "metadata_args" / Vec(U8)
)

# Define the full instruction layout
ME_MMM_CNFT_FULFILL_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_CNFT_FULFILL_BUY_ARGS
)

MPL_CORE_DEPOSIT_SELL_ARGS = CStruct(
    "allowlist_aux" / Option(String),
    "compression_proof" / Option(Vec(U8))
)

# Define the full instruction layout
ME_MMM_MPL_CORE_DEPOSIT_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / MPL_CORE_DEPOSIT_SELL_ARGS
)

EXT_DEPOSIT_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "allowlist_aux" / Option(String)
)

# Define the full instruction layout
ME_MMM_EXT_DEPOSIT_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / EXT_DEPOSIT_SELL_ARGS
)

OCP_WITHDRAW_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "allowlist_aux" / Option(String)
)

# Define the full instruction layout
ME_MMM_OCP_WITHDRAW_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / OCP_WITHDRAW_SELL_ARGS
)

UPDATE_POOL_ARGS = CStruct(
    "spot_price" / Option(U64),
    "curve_type" / Option(U8),
    "curve_delta" / Option(U64),
    "reinvest_fulfill_buy" / Option(U8), # bool
    "reinvest_fulfill_sell" / Option(U8), # bool
    "expiry" / Option(I64),
    "lp_fee_bp" / Option(U16),
    "referral" / Option(ConstructBytes (32)), # Pubkey
    "cosigner_annotation" / Option(ConstructBytes (32)),
    "buyside_creator_royalty_bp" / Option(U16)
)

# Define the full instruction layout
ME_MMM_UPDATE_POOL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / UPDATE_POOL_ARGS
)

SOL_EXT_FULFILL_BUY_ARGS = CStruct(
    "asset_amount" / U64,
    "min_payment_amount" / U64,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_EXT_FULFILL_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_EXT_FULFILL_BUY_ARGS
)

SOL_OCP_FULFILL_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "max_payment_amount" / U64,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_OCP_FULFILL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_OCP_FULFILL_SELL_ARGS
)

SOL_DEPOSIT_BUY_ARGS = CStruct(
    "payment_amount" / U64
)

# Define the full instruction layout
ME_MMM_SOL_DEPOSIT_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_DEPOSIT_BUY_ARGS
)

SOL_FULFILL_SELL_ARGS_V2 = CStruct(
    "asset_amount" / U64,
    "max_payment_amount" / U64,
    "buyside_creator_royalty_bp" / U16,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_FULFILL_SELL_LAYOUT_V2 = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_FULFILL_SELL_ARGS_V2
)

DEPOSIT_SELL_ARGS = CStruct(
    "asset_amount" / U64,
    "allowlist_aux" / Option(String)
)

# Define the full instruction layout
ME_MMM_DEPOSIT_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / DEPOSIT_SELL_ARGS
)

SOL_OCP_FULFILL_BUY_ARGS = CStruct(
    "asset_amount" / U64,
    "min_payment_amount" / U64,
    "allowlist_aux" / Option(String),
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

# Define the full instruction layout
ME_MMM_SOL_OCP_FULFILL_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SOL_OCP_FULFILL_BUY_ARGS
)

SET_SHARED_ESCROW_ARGS = CStruct(
    "shared_escrow_count" / U8
)

# Define the full instruction layout
ME_MMM_SET_SHARED_ESCROW_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / SET_SHARED_ESCROW_ARGS
)

CREATE_POOL_ARGS = CStruct(
    "spot_price" / U64,
    "curve_type" / U8,
    "curve_delta" / U64,
    "reinvest_fulfill_buy" / U8,  # bool
    "reinvest_fulfill_sell" / U8, # bool
    "expiry" / I64,
    "lp_fee_bp" / U16,
    "referral" / ConstructBytes (32), # Pubkey
    "cosigner_annotation" / ConstructBytes (32),
    "buyside_creator_royalty_bp" / U16,
    "pool_type" / U8,
    "uuid" / ConstructBytes (32), # Pubkey
    "payment_mint" / ConstructBytes (32), # Pubkey
    "allowlist_entries" / Option(Vec(ConstructBytes (32))) # Option<Vec<Pubkey>>
)

# Define the full instruction layout
ME_MMM_CREATE_POOL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / CREATE_POOL_ARGS
)

ALLOWLIST_ENTRY = CStruct(
    "key" / ConstructBytes (32), # Pubkey
    "value" / U8       # bool
)

# Define the nested arguments structure that contains a list of these entries
UPDATE_ALLOWLISTS_ARGS = CStruct(
    "allowlists" / Vec(ALLOWLIST_ENTRY)
)

# Define the full instruction layout
ME_MMM_UPDATE_ALLOWLISTS_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / UPDATE_ALLOWLISTS_ARGS
)

MIP1_EXECUTE_SALE_V2_ARGS = CStruct(
    "price" / U64,
    "maker_fee_bp" / U16,
    "taker_fee_bp" / U16
)
ME_V2_MIP1_EXECUTE_SALE_V2_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / MIP1_EXECUTE_SALE_V2_ARGS
)
ME_MMM_SOL_FULFILL_SELL_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "asset_amount" / U64,
    "max_payment_amount" / U64,
    "allowlist_aux" / String,
    "maker_fee_bp" / I16,
    "taker_fee_bp" / I16
)

TCOMP_BUY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "meta_hash" / ConstructBytes (32),
    "creator_shares" / Vec(U8),  # Vec<u8>
    "creator_verified" / Vec(U8),
    "seller_fee_basis_points" / U16,
    "max_amount" / U64,
    "optional_royalty_pct" / Option(U16),
)

TENSOR_CNFT_BUY_CORE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "max_amount" / U64
)

TENSOR_CNFT_BID_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "bid_id" / ConstructBytes (32),        # Pubkey
    "target" / U8,               # Enum
    "target_id" / ConstructBytes (32),     # Pubkey
    "field" / Option(U8),        # Enum
    "field_id" / Option(ConstructBytes (32)), # Pubkey
    "amount" / U64,
    "quantity" / U32,
    "expire_in_sec" / Option(U64),
    "currency" / Option(ConstructBytes (32)), # Pubkey
    "private_taker" / Option(ConstructBytes (32)), # Pubkey
    "maker_broker" / Option(ConstructBytes (32)) # Pubkey
)


TENSOR_CNFT_LIST_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "data_hash" / ConstructBytes (32),
    "creator_hash" / ConstructBytes (32),
    "amount" / U64,
    "expire_in_sec" / Option(U64),
    "currency" / Option(ConstructBytes (32)),     # Pubkey
    "private_taker" / Option(ConstructBytes (32)),# Pubkey
    "maker_broker" / Option(ConstructBytes (32))  # Pubkey
)

TENSOR_CNFT_EDIT_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "amount" / U64,
    "expire_in_sec" / Option(U64),
    "currency" / Option(ConstructBytes (32)),     # Pubkey
    "private_taker" / Option(ConstructBytes (32)),# Pubkey
    "maker_broker" / Option(ConstructBytes (32))  # Pubkey
)

TENSOR_CNFT_CANCEL_BID_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8)
)

TENSOR_CNFT_BUY_SPL_LAYOUT = TCOMP_BUY_LAYOUT

TENSOR_CNFT_DELIST_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "data_hash" / ConstructBytes (32),
    "creator_hash" / ConstructBytes (32)
)

TENSOR_CNFT_LIST_CORE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "amount" / U64,
    "expire_in_sec" / Option(U64),
    "currency" / Option(ConstructBytes (32)),     # Pubkey
    "private_taker" / Option(ConstructBytes (32)),# Pubkey
    "maker_broker" / Option(ConstructBytes (32))  # Pubkey
)

TENSOR_CNFT_TAKE_BID_LEGACY_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "min_amount" / U64,
    "optional_royalty_pct" / Option(U16),
    "rules_acc_present" / U8, # bool
    "authorization_data" / Option(Vec(U8))
)

TAKE_BID_FULL_META_ARGS = CStruct(
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "meta_args" / Vec(U8),
    "min_amount" / U64,
    "optional_royalty_pct" / Option(U16)
)

# Define the full instruction layout
TENSOR_CNFT_TAKE_BID_FULL_META_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "args" / TAKE_BID_FULL_META_ARGS
)

TENSOR_CNFT_DELIST_CORE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8)
)

TENSOR_CNFT_TAKE_BID_T22_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "min_amount" / U64
)

TENSOR_CNFT_TAKE_BID_WNS_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "min_amount" / U64
)

TENSOR_CNFT_TAKE_BID_META_HASH_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "meta_hash" / ConstructBytes (32),
    "creator_shares" / Vec(U8),
    "creator_verified" / Vec(U8), # Vec<bool>
    "seller_fee_basis_points" / U16,
    "min_amount" / U64,
    "optional_royalty_pct" / Option(U16)
)

TENSOR_CNFT_CLOSE_EXPIRED_LISTING_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "nonce" / U64,
    "index" / U32,
    "root" / ConstructBytes (32),
    "data_hash" / ConstructBytes (32),
    "creator_hash" / ConstructBytes (32)
)

TENSOR_CNFT_CLOSE_EXPIRED_BID_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8)
)

TENSOR_AMM_BUY_NFT_CORE_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "max_amount" / U64
)

TENSOR_AMM_BUY_NFT_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "max_amount" / U64,
    "authorization_data" / Option(Vec(U8)),
    "optional_royalty_pct" / Option(U16)
)
TENSOR_AMM_BUY_NFT_T22_LAYOUT = CStruct(
    "discriminator" / ConstructBytes (8),
    "max_amount" / U64
)
# =============================================================================
# DISCRIMINATOR MAPPINGS (Corrected with sighashes from IDLs and computed additions)
# =============================================================================
MARKETPLACE_DISCRIMINATORS = {
    'magic_eden_v2': {
        'buy': bytes.fromhex("4d8d1340beae1206"),  # buyV2
        'sell': bytes.fromhex("33e685a4017f83ad"),  # sell
        'mip1_sell': bytes.fromhex("3a32ac6fa697165e"),
        'mip1_sell_v2': bytes.fromhex("49d4f26419744186"),
        'mip1_sell_v3': bytes.fromhex("1ff3f73b8653a5da"),  # Discovered by learner (needs review)
        'core_sell': bytes.fromhex("e5585013a9364991"),
        'execute_sale': bytes.fromhex("80845dc2cd0368dc"),  # executeSaleV2
        'mip1_execute_sale_v2': bytes.fromhex("44e2b02f693242c1"),
        'core_execute_sale_v2': bytes.fromhex("b317486835261561"),
        'mip1_cancel_sell': bytes.fromhex("2c2484847c3fedb6"),
        'cancel_sell_v2': bytes.fromhex("c6c682cba35faf4b"),
        'core_cancel_sell': bytes.fromhex("8b5a75929665493b"),
        'cancel_sell': bytes.fromhex("7a9ba994d6df4168"),  # cancelSell
        'deposit': bytes.fromhex("f223c68952e1f2b6"),  # deposit
        'withdraw': bytes.fromhex("b712469c946da122"),  # withdraw
        'bid': bytes.fromhex("189f6234ab528fa1"),  # Legacy bid
        'cancel_bid': bytes.fromhex("7ad46e8c921f583d"),  # Legacy cancel_bid
        'list': bytes.fromhex("33e685a4017f83ad"),  # sell as list
        'delist': bytes.fromhex("7a9ba994d6df4168"),  # cancelSell as delist
        'update_auction_house': bytes.fromhex("bd6750836c37144c"),
    },
    'magic_eden_mmm': {
        'create_pool': bytes.fromhex("f4ec750412003e58"),  # createPool
        'update_pool': bytes.fromhex("55317abc354db884"),  # updatePool
        'sol_fulfill_buy': bytes.fromhex("97de2e3741a76cb1"),  # solFulfillBuy
        'sol_fulfill_sell': bytes.fromhex("45295bc43e5e43a1"),  # solFulfillSell
        'deposit_sell': bytes.fromhex("78a032b0510444bb"),  # depositSell
        'withdraw_sell': bytes.fromhex("7ef36c038082e10d"),  # withdrawSell
        'sol_ext_fulfill_sell': bytes.fromhex("b6611b8537449191"),
        'sol_mip1_fulfill_buy': bytes.fromhex("76c35fa87ee95225"),  # solMip1FulfillBuy
        'sol_mip1_fulfill_sell': bytes.fromhex("843a84a6a281b303"),
        'withdraw_by_mmm': bytes.fromhex("a783e0eb741f14f9"),  # withdrawByMmm
        'sol_mpl_core_fulfill_sell': bytes.fromhex("b0f806e237dfb899"),
        'mip1_withdraw_sell_v2': bytes.fromhex("ec529e7a0818af91"),
        'mip1_withdraw_sell': bytes.fromhex("b96d6790471b6f9a"),
        'mpl_core_withdraw_sell': bytes.fromhex("83faaa49e52e673a"), 
        'sol_withdraw_buy': bytes.fromhex("42dd8373855a9992"),
        'cnft_fulfill_buy': bytes.fromhex("b95425287c152199"),
        'mpl_core_deposit_sell': bytes.fromhex("8331032127027877"),
        'ext_deposit_sell': bytes.fromhex("9023410332215707"),
        'ocp_withdraw_sell': bytes.fromhex("a21ca7226c265e31"),
        'sol_ext_fulfill_buy': bytes.fromhex("83181829e52c80c5"),
        'sol_ocp_fulfill_sell': bytes.fromhex("83416b0b0a56e929"),
        'sol_deposit_buy': bytes.fromhex("c11961e891026048"),
        'sol_ocp_fulfill_buy': bytes.fromhex("3c8e47458622c544"),
        'set_shared_escrow': bytes.fromhex("5522f3c843818625"),
        'update_allowlists': bytes.fromhex("844318331818b871"),

            # Version 2 (from actual on-chain transactions):
    'update_pool_v2': bytes.fromhex("efd6aa4e24231e22"),
    'set_shared_escrow_v2': bytes.fromhex("c9a73c9a0718edf7"),
    },
    'tensor_cnft_marketplace': {  # TComp
        'list': bytes.fromhex("36aec14311298426"),  # list
        'list_core': bytes.fromhex("933397940733806d"),
        'delist': bytes.fromhex("3788cd6b6bad041f"),  # delist
        'delist_core': bytes.fromhex("b31092c5341c304f"),
        'buy': bytes.fromhex("66063d1201daebea"),  # buy
        'buy_spl': bytes.fromhex("92ccca556152abae"),  # buySpl
        'bid': bytes.fromhex("c738552692f3259e"),  # bid
        'cancel_bid': bytes.fromhex("6a8e437cae6a0c7d"),  # cancelBid
        'cancel_bid_v2': bytes.fromhex("28f3bed9d0fd56ce"),
        'take_bid': bytes.fromhex("b5c80a5f0eb09040"),  # takeBid
        'take_bid_spl': bytes.fromhex("b887b7cc87d4259e"),  # takeBidSpl
        'edit': bytes.fromhex("0fb72156571c9791"),  # edit
        'bid_v2_alt1': bytes.fromhex("8704a37e0ea89957"), 
        'bid_v2_alt2': bytes.fromhex("8704a37e0ea89958"),
        'buy_core': bytes.fromhex("52f481e1951591f4"),
        'take_bid_legacy': bytes.fromhex("b98200f86a345155"),
        'take_bid_full_meta': bytes.fromhex("805185956f421932"),
        'take_bid_t22': bytes.fromhex("991244304c442735"),
        'take_bid_wns': bytes.fromhex("b7713d191a4e1d1f"),
        'take_bid_meta_hash': bytes.fromhex("79918009e3b25595"),
        'close_expired_listing': bytes.fromhex("012a815a7727142b"),
        'close_expired_bid': bytes.fromhex("128c18782a93325a"),

    },
    'tensor_escrow': {  # TensorSwap
        'init_pool': bytes.fromhex("0281985edd28635e"),  # initPool
        'close_pool': bytes.fromhex("4efda51b9fb91dec"),  # closePool
        'deposit_nft': bytes.fromhex("dac2ba41884d4cb7"),  # depositNft
        'withdraw_nft_sol': bytes.fromhex("87e14d5a30da1fd4"),  # withdrawNftSol
        'withdraw_nft_trade': bytes.fromhex("e11ab4fea76c511f"),  # withdrawNftTrade
        'buy_nft': bytes.fromhex("4f7a05d6b38a2a5c"),  # buyNft
        'sell_nft_token_pool': bytes.fromhex("0393ff7d1fdd79b6"),  # sellNftTokenPool
        'sell_nft_trade_pool': bytes.fromhex("eb571e720e6b2148"),  # sellNftTradePool
        'edit_pool': bytes.fromhex("01f7e968652bbed2"),  # editPool
        'take_snipe': bytes.fromhex("ac9ca7caceb892a5"),  # takeSnipe
        'take_snipe_v2': bytes.fromhex("7eb310e6dfd1b3f1"),  # takeSnipeV2
        'withdraw_tswap_fees': bytes.fromhex("4d9c156bc5987628"),  # withdrawTswapFees
        'withdraw_mm_fees': bytes.fromhex("c4980c417a5b7c14"),  # withdrawMmFees
        'withdraw_mm_fees_v2': bytes.fromhex("facbf23607f56345"),  # withdrawMmFeesV2
        'list': bytes.fromhex("36aec14311298426"),  # Placeholder for list if applicable
        'delist': bytes.fromhex("3788cd6b6bad041f"),  # Placeholder for delist
    },
    'tensor_amm': {
        'create_pool': bytes.fromhex("f4ec750412003e58"),  # createPool
        'edit_pool': bytes.fromhex("01f7e968652bbed2"),  # editPool
        'close_pool': bytes.fromhex("4efda51b9fb91dec"),  # closePool
        'deposit_sol': bytes.fromhex("ea2547ee8871ffc4"),  # depositSol
        'withdraw_sol': bytes.fromhex("741ce3650e1880a0"),  # withdrawSol
        'buy_nft': bytes.fromhex("4f7a05d6b38a2a5c"),  # buyNft
        'buy_nft_core': bytes.fromhex("b96c568f76e330a1"), 
        'buy_nft_t22': bytes.fromhex("805e5022c2445653"),
        'sell_nft_token_pool': bytes.fromhex("0393ff7d1fdd79b6"),  # sellNftTokenPool
        'sell_nft_trade_pool': bytes.fromhex("eb571e720e6b2148"),  # sellNftTradePool
        'deposit_nft': bytes.fromhex("dac2ba41884d4cb7"),  # depositNft
        'withdraw_nft': bytes.fromhex("ec10a6b791a04c56"),  # withdrawNft
        'withdraw_fees': bytes.fromhex("bfff45a379070fe2"),  # withdrawFees
    },
    'haus': {
        'withdraw_from_fee': bytes.fromhex("f92220cd99c1ace5"),  # withdrawFromFee
        'withdraw_from_treasury': bytes.fromhex("4aaf7c8f2b37f9fc"),  # withdrawFromTreasury
        'update_auction_house': bytes.fromhex("bd6750836c37144c"),  # updateAuctionHouse
        'create_auction_house': bytes.fromhex("67ed663e71e9b980"),  # createAuctionHouse
        'buy': bytes.fromhex("66063d1201daebea"),  # buy
        'public_buy': bytes.fromhex("c6c55618925fd148"),  # publicBuy
        'sell': bytes.fromhex("33e685a4017f83ad"),  # sell
        'execute_sale': bytes.fromhex("872433ebac772bb9"),  # executeSale
        'cancel': bytes.fromhex("e8dbdf29dbecdcbe"),  # cancel
        'deposit': bytes.fromhex("f223c68952e1f2b6"),  # deposit
        'withdraw': bytes.fromhex("b712469c946da122"),  # withdraw
        'mip1_cancel_sell': bytes.fromhex("2c2484847c3fedb6"),  # mip1CancelSell
        'sol_mip1_fulfill_buy': bytes.fromhex("76c35fa87ee95225"),  # solMip1FulfillBuy
    },
    'opensea': {
        'buy': bytes.fromhex("66063d1201daebea"),  # buy
        'sell': bytes.fromhex("33e685a4017f83ad"),  # sell
        'list': bytes.fromhex("36aec14311298426"),  # list
        'delist': bytes.fromhex("3788cd6b6bad041f"),  # delist
        'bid': bytes.fromhex("c738552692f3259e"),  # bid
        'cancel_bid': bytes.fromhex("6a8e437cae6a0c7d"),  # cancelBid
    },
    # Unified Tensor mapping for backward compatibility
    'tensor': {
        'buy': bytes.fromhex("66063d1201daebea"),  # buy (TComp/AMM)
        'sell': bytes.fromhex("0393ff7d1fdd79b6"),  # sellNftTokenPool
        'list': bytes.fromhex("36aec14311298426"),  # list (TComp)
        'delist': bytes.fromhex("3788cd6b6bad041f"),  # delist (TComp)
        'bid': bytes.fromhex("c738552692f3259e"),  # bid (TComp)
        'cancel_bid': bytes.fromhex("6a8e437cae6a0c7d"),  # cancelBid (TComp)
    },
}

# =============================================================================
# EVENT TYPE MAPPINGS (Enhanced with additions)
# =============================================================================
EVENT_TYPE_MAPPING = {
    # Core marketplace actions
    'buy': 'NFT_SALE',
    'buy_nft': 'NFT_SALE',
    'buy_spl': 'NFT_SALE',
    'sell': 'NFT_SALE',
    'sell_nft_token': 'NFT_SALE',
    'sell_nft_token_pool': 'NFT_SALE',
    'sell_nft_trade': 'NFT_SALE',
    'sell_nft_trade_pool': 'NFT_SALE',
    'execute_sale': 'NFT_SALE',
    'fulfill_buy': 'NFT_SALE',
    'fulfill_sell': 'NFT_SALE',
    'sol_mip1_fulfill_buy': 'NFT_SALE',
    'public_buy': 'NFT_SALE',
    
    'list': 'NFT_LISTING',
    'delist': 'NFT_CANCEL_LISTING',
    'cancel_sell': 'NFT_CANCEL_LISTING',
    'mip1_cancel_sell': 'NFT_CANCEL_LISTING',
    
    'bid': 'NFT_BID',
    'bid_v2_alt1': 'NFT_BID',
    'bid_v2_alt2': 'NFT_BID',
    'cancel_bid': 'NFT_BID_CANCELLED',
    
    # Pool operations
    'deposit_sol': 'NFT_POOL_DEPOSIT',
    'withdraw_sol': 'NFT_POOL_WITHDRAW',
    'deposit_nft': 'NFT_POOL_DEPOSIT',
    'withdraw_nft': 'NFT_POOL_WITHDRAW',
    'withdraw_nft_sol': 'NFT_POOL_WITHDRAW',
    'withdraw_nft_trade': 'NFT_POOL_WITHDRAW',
    'deposit_sell': 'NFT_POOL_DEPOSIT',
    'withdraw_sell': 'NFT_POOL_WITHDRAW',
    'init_pool': 'NFT_POOL_INIT',
    'close_pool': 'NFT_POOL_CLOSE',
    'create_pool': 'NFT_POOL_INIT',
    'update_pool': 'NFT_POOL_UPDATE',
    'withdraw_by_mmm': 'NFT_POOL_WITHDRAW',
    
    # Escrow/deposit operations
    'deposit': 'NFT_BID',  # Depositing for bid = placing bid
    'withdraw': 'NFT_BID_CANCELLED',  # Withdrawing = cancelled bid
    
    # Edit operations
    'edit': 'NFT_LISTING_UPDATE',
    'edit_pool': 'NFT_POOL_UPDATE',
    'update_auction_house': 'NFT_POOL_UPDATE',
    
    # Fee withdrawals
    'withdraw_from_fee': 'NFT_POOL_WITHDRAW',
    'withdraw_from_treasury': 'NFT_POOL_WITHDRAW',
    'withdraw_fees': 'NFT_POOL_WITHDRAW',
    'withdraw_tswap_fees': 'NFT_POOL_WITHDRAW',
    'withdraw_mm_fees': 'NFT_POOL_WITHDRAW',
    'withdraw_mm_fees_v2': 'NFT_POOL_WITHDRAW',
    
    # Other
    'take_bid': 'NFT_SALE',
    'take_bid_spl': 'NFT_SALE',
    'take_snipe': 'NFT_SALE',
    'take_snipe_v2': 'NFT_SALE',
    'cancel': 'NFT_CANCEL_LISTING',
    'thaw_delegated_account': 'NFT_POOL_UPDATE',  # Placeholder
    'create_trade_state': 'NFT_LISTING',
    'auctioneer_withdraw': 'NFT_POOL_WITHDRAW',
    'auctioneer_buy': 'NFT_SALE',
    'auctioneer_public_buy': 'NFT_SALE',
    'auctioneer_sell': 'NFT_SALE',
    'auctioneer_execute_sale': 'NFT_SALE',
    'auctioneer_cancel': 'NFT_CANCEL_LISTING',
    'auctioneer_deposit': 'NFT_POOL_DEPOSIT',
    'auctioneer_withdraw_from_fee': 'NFT_POOL_WITHDRAW',
    'create_auctioneer': 'NFT_POOL_INIT',
    'update_auctioneer': 'NFT_POOL_UPDATE',
    'create_auctioneer_trade_state': 'NFT_LISTING',
    'withdraw_from_treasury': 'NFT_POOL_WITHDRAW',
}

# =============================================================================
# MARKETPLACE NORMALIZATION
# =============================================================================
MARKETPLACE_ALIASES = {
    # Tensor normalization - all Tensor programs map to 'tensor'
    'tensor_marketplace': 'tensor',
    'tensor_cnft_marketplace': 'tensor',
    'tensor_amm': 'tensor', 
    'tensor_escrow': 'tensor',
    
    # Magic Eden normalization
    'magic_eden': 'magic_eden_v2',
    'magiceden': 'magic_eden_v2',
    'me': 'magic_eden_v2',
    
    # OpenSea normalization  
    'opensea_solana': 'opensea',
    'os': 'opensea',
}


# =============================================================================
# UTILITY FUNCTIONS (Enhanced)
# =============================================================================

def get_discriminator_length(marketplace: str) -> int:
    """All marketplaces use 8-byte discriminators."""
    return 8

def get_marketplace_from_program_id(program_id: str) -> str:
    """Get marketplace name from program ID."""
    for marketplace, pid in MARKETPLACE_PROGRAMS.items():
        if pid == program_id:
            return marketplace
    return 'unknown'

def normalize_marketplace_name(raw_marketplace: str) -> str:
    """Normalize marketplace names to standardized format."""
    if not raw_marketplace:
        return 'unknown'
    return MARKETPLACE_ALIASES.get(raw_marketplace.lower(), raw_marketplace.lower())

def identify_instruction(marketplace: str, discriminator: bytes) -> str:
    """Identify instruction type from discriminator."""
    if marketplace not in MARKETPLACE_DISCRIMINATORS:
        return 'unknown'
    
    discriminators = MARKETPLACE_DISCRIMINATORS[marketplace]
    for action, disc in discriminators.items():
        if discriminator == disc:
            return action
    return 'unknown'

def identify_tensor_instruction(program_id: str, discriminator: bytes) -> str:
    """Identify Tensor instruction by specific program and discriminator."""
    # Handle the specific program IDs based on the new, correct discriminator maps
    if program_id == MARKETPLACE_PROGRAMS.get('tensor_amm'):
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_amm', {}).items():
            if discriminator == disc:
                return f"amm_{action}"
    elif program_id == MARKETPLACE_PROGRAMS.get('tensor_cnft_marketplace'):
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_cnft_marketplace', {}).items():
            if discriminator == disc:
                return f"cnft_{action}"
    elif program_id == MARKETPLACE_PROGRAMS.get('tensor_escrow'):
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_escrow', {}).items():
            if discriminator == disc:
                return f"escrow_{action}"
    
    # If no match is found in the specific program maps, return unknown
    return 'unknown'


def get_event_type(action: str) -> str:
    """Get standardized event type from action."""
    return EVENT_TYPE_MAPPING.get(action.lower(), action.upper())

def detect_marketplace_from_programs(program_ids: List[str]) -> str:
    """Detect marketplace from transaction program IDs with priority order."""
    for prog_id in program_ids:
        marketplace = get_marketplace_from_program_id(prog_id)
        if marketplace != 'unknown':
            return normalize_marketplace_name(marketplace)
    return 'unknown'

def get_discriminators_for_marketplace(marketplace: str) -> dict:
    """Get discriminators for a marketplace, handling aliases."""
    normalized = normalize_marketplace_name(marketplace)
    
    # Handle Tensor special case - multiple program types
    if normalized == 'tensor':
        tensor_discriminators = {}
        
        # Add AMM discriminators
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_amm', {}).items():
            tensor_discriminators[f'amm_{action}'] = disc
            
        # Add cNFT Marketplace discriminators  
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_cnft_marketplace', {}).items():
            tensor_discriminators[f'cnft_{action}'] = disc
            
        # Add Escrow discriminators
        for action, disc in MARKETPLACE_DISCRIMINATORS.get('tensor_escrow', {}).items():
            tensor_discriminators[f'escrow_{action}'] = disc
            
        # Add generic Tensor discriminators
        tensor_discriminators.update(MARKETPLACE_DISCRIMINATORS.get('tensor', {}))
            
        return tensor_discriminators
    
    return MARKETPLACE_DISCRIMINATORS.get(normalized, {})

def get_tensor_program_type(program_id: str) -> str:
    """Get the type of Tensor program from program ID."""
    if program_id == MARKETPLACE_PROGRAMS.get('tensor_amm'):
        return 'amm'
    elif program_id == MARKETPLACE_PROGRAMS.get('tensor_cnft_marketplace'):
        return 'marketplace'
    elif program_id == MARKETPLACE_PROGRAMS.get('tensor_escrow'):
        return 'escrow'
    return 'unknown'

def identify_instruction_enhanced(program_id: str, discriminator: bytes) -> tuple[str, str]:
    marketplace = get_marketplace_from_program_id(program_id)
    if marketplace == 'unknown':
        return 'unknown', 'unknown'
    
    if marketplace.startswith('tensor_'):
        action = identify_tensor_instruction(program_id, discriminator)
        return normalize_marketplace_name(marketplace), action
    
    action = identify_instruction(marketplace, discriminator)
    return normalize_marketplace_name(marketplace), action

# Validate that MARKETPLACE_PROGRAMS is not empty
if not MARKETPLACE_PROGRAMS:
    import logging
    logger = logging.getLogger(__name__)
    logger.error("=" * 80)
    logger.error("CRITICAL ERROR: MARKETPLACE_PROGRAMS is empty!")
    logger.error("WebSocket subscriptions will not work!")
    logger.error("=" * 80)