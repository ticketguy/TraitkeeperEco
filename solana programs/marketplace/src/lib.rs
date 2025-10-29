// --- marketplace/src/lib.rs ---

use anchor_lang::prelude::*;
use anchor_lang::solana_program::{system_instruction, sysvar::clock::Clock};
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer, CloseAccount};
use std::cmp::min;

// This must be the program ID of your compiled Quest Program
use quest_program::cpi::accounts::{PayNegotiationRebate, PayAuctionLoserRebate, UpdateProgress};
use quest_program::program::QuestProgram;
use quest_program::{self, QuestActionType}; // Import the enum

declare_id!(" MARKETPLACE_PROGRAM_ID_HERE ");

#[program]
pub mod marketplace {
    use super::*;

    // --- 1. ADMIN INSTRUCTIONS ---

    pub fn initialize_config(
        ctx: Context<InitializeConfig>,
        platform_fee_bps: u16,
        max_royalty_subsidy_bps: u16,
        min_vitality_for_rebate: u8,
        rebate_counter_min: u8,
        auction_loser_rebate_lamports: u64,
    ) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.admin = *ctx.accounts.admin.key;
        
        // Wallets
        config.fee_wallet = *ctx.accounts.fee_wallet.key;
        config.quest_wallet = *ctx.accounts.quest_wallet.key;
        config.vault_wallet = *ctx.accounts.vault_wallet.key;

        // External Programs & Authorities
        config.quest_program = *ctx.accounts.quest_program.key;
        config.program_authority_bump = ctx.bumps.program_authority;

        // Rules
        config.platform_fee_bps = platform_fee_bps;
        config.max_royalty_subsidy_bps = max_royalty_subsidy_bps;
        config.min_vitality_for_rebate = min_vitality_for_rebate;
        config.rebate_counter_min = rebate_counter_min;
        config.auction_loser_rebate_lamports = auction_loser_rebate_lamports;

        Ok(())
    }

    pub fn update_config_rules(
        ctx: Context<UpdateConfig>,
        platform_fee_bps: u16,
        max_royalty_subsidy_bps: u16,
        min_vitality_for_rebate: u8,
        rebate_counter_min: u8,
        auction_loser_rebate_lamports: u64,
    ) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.platform_fee_bps = platform_fee_bps;
        config.max_royalty_subsidy_bps = max_royalty_subsidy_bps;
        config.min_vitality_for_rebate = min_vitality_for_rebate;
        config.rebate_counter_min = rebate_counter_min;
        config.auction_loser_rebate_lamports = auction_loser_rebate_lamports;
        Ok(())
    }

    pub fn update_config_wallets(
        ctx: Context<UpdateConfig>,
        fee_wallet: Pubkey,
        quest_wallet: Pubkey,
        vault_wallet: Pubkey,
        quest_program: Pubkey,
    ) -> Result<()> {
        let config = &mut ctx.accounts.config;
        config.fee_wallet = fee_wallet;
        config.quest_wallet = quest_wallet;
        config.vault_wallet = vault_wallet;
        config.quest_program = quest_program;
        Ok(())
    }

    // --- 2. LISTING / DIRECT SELL INSTRUCTIONS ---

    pub fn list_nft(
        ctx: Context<ListNft>,
        price_lamports: u64,
        list_type: ListingType,
    ) -> Result<()> {
        // ... (Same as before: validate price, create listing, transfer NFT to vault) ...
        if price_lamports == 0 {
            return err!(MarketplaceError::InvalidPrice);
        }

        let listing = &mut ctx.accounts.listing_account;
        listing.seller = *ctx.accounts.seller.key;
        listing.nft_mint = ctx.accounts.nft_mint.key();
        listing.price_lamports = price_lamports;
        listing.list_type = list_type;
        listing.bump = ctx.bumps.listing_account;
        
        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.seller_token_account.to_account_info(),
                    to: ctx.accounts.nft_vault.to_account_info(),
                    authority: ctx.accounts.seller.to_account_info(),
                },
            ),
            1,
        )?;

        // --- CPI to Quest Program ---
        helpers::cpi_update_quest_progress(
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            &ctx.accounts.quest_user_account,
            &ctx.accounts.seller,
            &ctx.accounts.system_program,
            ctx.accounts.config.program_authority_bump,
            QuestActionType::List,
        )?;

        emit!(Listed {
            seller: listing.seller,
            nft_mint: listing.nft_mint,
            price: price_lamports,
            list_type
        });

        Ok(())
    }

    pub fn unlist_nft(ctx: Context<UnlistNft>) -> Result<()> {
        // ... (Same as before: transfer NFT back, close vault) ...
        let listing = &ctx.accounts.listing_account;

        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.nft_vault.to_account_info(),
                    to: ctx.accounts.seller_token_account.to_account_info(),
                    authority: ctx.accounts.listing_account.to_account_info(),
                },
                &[&[
                    LISTING_SEED,
                    listing.seller.as_ref(),
                    listing.nft_mint.as_ref(),
                    &[listing.bump],
                ]],
            ),
            1,
        )?;

        token::close_account(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                CloseAccount {
                    account: ctx.accounts.nft_vault.to_account_info(),
                    destination: ctx.accounts.seller.to_account_info(),
                    authority: ctx.accounts.listing_account.to_account_info(),
                },
                &[&[
                    LISTING_SEED,
                    listing.seller.as_ref(),
                    listing.nft_mint.as_ref(),
                    &[listing.bump],
                ]],
            )
        )?;

        emit!(Unlisted {
            seller: listing.seller,
            nft_mint: listing.nft_mint
        });
        Ok(())
    }

    pub fn buy_listed_nft(ctx: Context<BuyListedNft>, royalty_bps: u16) -> Result<()> {
        let listing = &ctx.accounts.listing_account;
        let buyer = &ctx.accounts.buyer;
        let seller = &ctx.accounts.seller;
        let config = &ctx.accounts.config;

        if buyer.key() == listing.seller {
            return err!(MarketplaceError::OwnerCannotBuy);
        }

        let sale_price = listing.price_lamports;
        
        // --- 1. Handle Payment, Fees, and Royalties ---
        helpers::handle_payment_and_royalties(
            config.to_account_info(),
            ctx.accounts.fee_wallet.to_account_info(),
            ctx.accounts.quest_wallet.to_account_info(), // 30% fee split goes here
            ctx.accounts.vault_wallet.to_account_info(),
            buyer.to_account_info(), // Source of funds
            seller.to_account_info(),
            &ctx.remaining_accounts, // Royalty creators
            ctx.accounts.system_program.to_account_info(),
            None, // No signer seeds, buyer is signing
            sale_price,
            royalty_bps,
            config.platform_fee_bps,
            config.max_royalty_subsidy_bps,
            // Subsidy logic
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            config.program_authority_bump,
        )?;

        // --- 2. Transfer NFT & Close Vault ---
        // ... (Same as before) ...
        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.nft_vault.to_account_info(),
                    to: ctx.accounts.buyer_token_account.to_account_info(),
                    authority: ctx.accounts.listing_account.to_account_info(),
                },
                &[&[
                    LISTING_SEED,
                    listing.seller.as_ref(),
                    listing.nft_mint.as_ref(),
                    &[listing.bump],
                ]],
            ),
            1,
        )?;
        token::close_account(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                CloseAccount {
                    account: ctx.accounts.nft_vault.to_account_info(),
                    destination: seller.to_account_info(),
                    authority: ctx.accounts.listing_account.to_account_info(),
                },
                &[&[
                    LISTING_SEED,
                    listing.seller.as_ref(),
                    listing.nft_mint.as_ref(),
                    &[listing.bump],
                ]],
            )
        )?;

        // --- 3. CPI to Quest Program ---
        helpers::cpi_update_quest_progress(
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            &ctx.accounts.quest_user_account,
            &ctx.accounts.buyer,
            &ctx.accounts.system_program,
            ctx.accounts.config.program_authority_bump,
            QuestActionType::Buy,
        )?;

        emit!(Sale {
            seller: listing.seller,
            buyer: *buyer.key,
            nft_mint: listing.nft_mint,
            price: sale_price
        });

        Ok(())
    }

    // --- 3. PRIVATE BID INSTRUCTIONS ---

    pub fn place_private_bid(
        ctx: Context<PlacePrivateBid>,
        amount_lamports: u64,
        expiry_hours: u64,
        nft_vitality_score: u8,
        negotiation_count: u8,
    ) -> Result<()> {
        // ... (Same as before: validate, create bid account, escrow SOL) ...
        let clock = Clock::get()?;
        let config = &ctx.accounts.config;
        
        if amount_lamports == 0 { return err!(MarketplaceError::InvalidPrice); }
        if ctx.accounts.bidder.key() == ctx.accounts.nft_owner.key() { return err!(MarketplaceError::OwnerCannotBid); }

        let bid = &mut ctx.accounts.bid_account;
        bid.bidder = *ctx.accounts.bidder.key;
        bid.nft_mint = ctx.accounts.nft_mint.key();
        bid.owner_at_creation = ctx.accounts.nft_owner.key();
        bid.amount_lamports = amount_lamports;
        bid.expires_at = clock.unix_timestamp + (expiry_hours as i64 * 3600);
        bid.status = BidStatus::Active;
        bid.bump = ctx.bumps.bid_account;
        bid.is_rebate_eligible = nft_vitality_score >= config.min_vitality_for_rebate;
        bid.negotiation_count = negotiation_count;

        anchor_lang::solana_program::program::invoke(
            &system_instruction::transfer(
                ctx.accounts.bidder.key,
                &bid.key(),
                amount_lamports,
            ),
            &[
                ctx.accounts.bidder.to_account_info(),
                bid.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
        )?;

        // --- CPI to Quest Program ---
        helpers::cpi_update_quest_progress(
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            &ctx.accounts.quest_user_account,
            &ctx.accounts.bidder,
            &ctx.accounts.system_program,
            ctx.accounts.config.program_authority_bump,
            QuestActionType::Bid,
        )?;

        emit!(BidPlaced {
            bid_id: bid.key(),
            bidder: bid.bidder,
            nft_mint: bid.nft_mint,
            amount: bid.amount_lamports
        });

        Ok(())
    }

    pub fn cancel_private_bid(ctx: Context<ManagePrivateBid>) -> Result<()> {
        // ... (Same as before: set status to Cancelled) ...
        let bid = &mut ctx.accounts.bid_account;
        if bid.status != BidStatus::Active { return err!(MarketplaceError::BidNotActive); }
        bid.status = BidStatus::Cancelled;
        emit!(BidCancelled { bid_id: bid.key() });
        Ok(())
    }

    pub fn reject_private_bid(ctx: Context<ManagePrivateBid>) -> Result<()> {
        // ... (Same as before: set status to Rejected) ...
        let bid = &mut ctx.accounts.bid_account;
        if bid.status != BidStatus::Active { return err!(MarketplaceError::BidNotActive); }
        bid.status = BidStatus::Rejected;
        emit!(BidRejected { bid_id: bid.key() });
        Ok(())
    }

    pub fn accept_private_bid(ctx: Context<AcceptPrivateBid>, royalty_bps: u16) -> Result<()> {
        // ... (Same as before: validate bid) ...
        let clock = Clock::get()?;
        let bid = &mut ctx.accounts.bid_account;
        let config = &ctx.accounts.config;
        
        if bid.status != BidStatus::Active { return err!(MarketplaceError::BidNotActive); }
        if clock.unix_timestamp > bid.expires_at {
            bid.status = BidStatus::Expired;
            return err!(MarketplaceError::BidExpired);
        }
        
        bid.status = BidStatus::Accepted;
        let sale_price = bid.amount_lamports;
        
        // --- 1. Handle Payment, Fees, and Royalties ---
        let bid_signer_seeds = &[
            BID_SEED,
            bid.bidder.as_ref(),
            bid.nft_mint.as_ref(),
            &[bid.bump],
        ];
        
        helpers::handle_payment_and_royalties(
            config.to_account_info(),
            ctx.accounts.fee_wallet.to_account_info(),
            ctx.accounts.quest_wallet.to_account_info(),
            ctx.accounts.vault_wallet.to_account_info(),
            bid.to_account_info(), // Source of funds
            ctx.accounts.seller.to_account_info(),
            &ctx.remaining_accounts, // Royalty creators
            ctx.accounts.system_program.to_account_info(),
            Some(&[bid_signer_seeds]), // Bid PDA is signing
            sale_price,
            royalty_bps,
            config.platform_fee_bps,
            config.max_royalty_subsidy_bps,
            // Subsidy logic
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            config.program_authority_bump,
        )?;

        // --- 2. Transfer NFT ---
        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.seller_token_account.to_account_info(),
                    to: ctx.accounts.bidder_token_account.to_account_info(),
                    authority: ctx.accounts.seller.to_account_info(),
                },
            ),
            1,
        )?;

        // --- 3. Handle Negotiation Rebate (CPI to Quest Program) ---
        if bid.is_rebate_eligible && bid.negotiation_count >= config.rebate_counter_min {
            let rebate_amount = (sale_price * 50) / 10_000; // 0.5% rebate
            
            let cpi_program = ctx.accounts.quest_program.to_account_info();
            let cpi_accounts = PayNegotiationRebate {
                quest_wallet: ctx.accounts.quest_wallet.to_account_info(),
                bidder: ctx.accounts.bidder.to_account_info(),
                program_authority: ctx.accounts.program_authority.to_account_info(),
                system_program: ctx.accounts.system_program.to_account_info(),
            };
            let authority_seeds = &[
                PROGRAM_AUTHORITY_SEED,
                &[config.program_authority_bump],
            ];
            let signer_seeds = &[&authority_seeds[..]];

            quest_program::cpi::pay_negotiation_rebate(
                CpiContext::new_with_signer(cpi_program, cpi_accounts, signer_seeds),
                rebate_amount
            )?;
        }

        // --- 4. CPI to Quest Program ---
        helpers::cpi_update_quest_progress(
            &ctx.accounts.quest_program,
            &ctx.accounts.program_authority,
            &ctx.accounts.quest_user_account,
            &ctx.accounts.bidder,
            &ctx.accounts.system_program,
            ctx.accounts.config.program_authority_bump,
            QuestActionType::Buy,
        )?;

        emit!(BidAccepted { bid_id: bid.key() });
        emit!(Sale {
            seller: *ctx.accounts.seller.key,
            buyer: bid.bidder,
            nft_mint: bid.nft_mint,
            price: sale_price
        });

        Ok(())
    }

    // --- 4. AUCTION INSTRUCTIONS ---

    pub fn create_auction(
        ctx: Context<CreateAuction>,
        starting_price: u64,
        duration_hours: i64,
    ) -> Result<()> {
        // ... (Same as before: create auction account, escrow NFT) ...
        let clock = Clock::get()?;
        let auction = &mut ctx.accounts.auction_account;

        if starting_price == 0 { return err!(MarketplaceError::InvalidPrice); }

        auction.creator = *ctx.accounts.creator.key;
        auction.nft_mint = ctx.accounts.nft_mint.key();
        auction.end_time = clock.unix_timestamp + (duration_hours * 3600);
        auction.starting_price = starting_price;
        auction.current_bid = 0;
        auction.current_bidder = Pubkey::default();
        auction.status = AuctionStatus::Active;
        auction.bump = ctx.bumps.auction_account;

        token::transfer(
            CpiContext::new(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.creator_token_account.to_account_info(),
                    to: ctx.accounts.nft_vault.to_account_info(),
                    authority: ctx.accounts.creator.to_account_info(),
                },
            ),
            1,
        )?;
        
        emit!(AuctionCreated {
            auction_id: auction.key(),
            creator: auction.creator,
            nft_mint: auction.nft_mint,
            ends_at: auction.end_time
        });
        
        Ok(())
    }

    pub fn place_auction_bid(ctx: Context<PlaceAuctionBid>, amount: u64) -> Result<()> {
        // ... (Same as before: validate bid) ...
        let clock = Clock::get()?;
        let auction = &mut ctx.accounts.auction_account;
        let config = &ctx.accounts.config;
        
        if auction.status != AuctionStatus::Active { return err!(MarketplaceError::AuctionNotActive); }
        if clock.unix_timestamp >= auction.end_time { return err!(MarketplaceError::AuctionEnded); }
        if ctx.accounts.bidder.key() == auction.creator { return err!(MarketplaceError::OwnerCannotBid); }

        let min_bid = if auction.current_bid == 0 { auction.starting_price } else { auction.current_bid };
        if amount <= min_bid { return err!(MarketplaceError::BidTooLow); }

        // --- 1. Refund previous bidder & CPI to Quest Program for Rebate ---
        if auction.current_bidder != Pubkey::default() {
            // previous_bid_account is closed to previous_bidder (refunds SOL)
            
            // CPI to pay loser rebate
            let cpi_program = ctx.accounts.quest_program.to_account_info();
            let cpi_accounts = PayAuctionLoserRebate {
                quest_wallet: ctx.accounts.quest_wallet.to_account_info(),
                loser_bidder: ctx.accounts.previous_bidder.to_account_info(),
                program_authority: ctx.accounts.program_authority.to_account_info(),
                system_program: ctx.accounts.system_program.to_account_info(),
            };
            let authority_seeds = &[
                PROGRAM_AUTHORITY_SEED,
                &[config.program_authority_bump],
            ];
            let signer_seeds = &[&authority_seeds[..]];

            quest_program::cpi::pay_auction_loser_rebate(
                CpiContext::new_with_signer(cpi_program, cpi_accounts, signer_seeds),
                config.auction_loser_rebate_lamports
            )?;
        }

        // --- 2. Escrow new bid ---
        // ... (Same as before) ...
        let bid_account = &mut ctx.accounts.new_bid_account;
        bid_account.bidder = *ctx.accounts.bidder.key;
        bid_account.amount = amount;
        bid_account.bump = ctx.bumps.new_bid_account;

        anchor_lang::solana_program::program::invoke(
            &system_instruction::transfer(
                ctx.accounts.bidder.key,
                &bid_account.key(),
                amount,
            ),
            &[
                ctx.accounts.bidder.to_account_info(),
                bid_account.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
        )?;

        // --- 3. Update auction state ---
        auction.current_bid = amount;
        auction.current_bidder = *ctx.accounts.bidder.key;

        emit!(AuctionBid {
            auction_id: auction.key(),
            bidder: *ctx.accounts.bidder.key,
            amount
        });

        Ok(())
    }

    pub fn finalize_auction(ctx: Context<FinalizeAuction>, royalty_bps: u16) -> Result<()> {
        // ... (Same as before: validate auction end) ...
        let clock = Clock::get()?;
        let auction = &mut ctx.accounts.auction_account;
        let config = &ctx.accounts.config;

        if auction.status != AuctionStatus::Active { return err!(MarketplaceError::AuctionNotActive); }
        if clock.unix_timestamp < auction.end_time { return err!(MarketplaceError::AuctionNotEnded); }

        auction.status = AuctionStatus::Completed;
        
        let auction_key = auction.key();
        let vault_signer_seeds = &[
            AUCTION_VAULT_SEED,
            auction_key.as_ref(),
            &[ctx.bumps.nft_vault],
        ];

        if auction.current_bidder == Pubkey::default() {
            // --- SCENARIO A: NO BIDS ---
            // ... (Same as before: return NFT) ...
            auction.status = AuctionStatus::Cancelled;
            token::transfer(
                CpiContext::new_with_signer(
                    ctx.accounts.token_program.to_account_info(),
                    Transfer {
                        from: ctx.accounts.nft_vault.to_account_info(),
                        to: ctx.accounts.creator_token_account.to_account_info(),
                        authority: ctx.accounts.nft_vault.to_account_info(),
                    },
                    &[vault_signer_seeds],
                ),
                1,
            )?;
        } else {
            // --- SCENARIO B: THERE IS A WINNER ---
            let sale_price = auction.current_bid;
            auction.winner = auction.current_bidder;
            auction.final_price = sale_price;
            
            // 1. Handle Payment, Fees, and Royalties
            let bid_account_seeds = &[
                AUCTION_BID_SEED,
                auction_key.as_ref(),
                auction.current_bidder.as_ref(),
                &[ctx.accounts.highest_bid_account.as_ref().unwrap().bump],
            ];
            
            helpers::handle_payment_and_royalties(
                config.to_account_info(),
                ctx.accounts.fee_wallet.to_account_info(),
                ctx.accounts.quest_wallet.to_account_info(),
                ctx.accounts.vault_wallet.to_account_info(),
                ctx.accounts.highest_bid_account.as_ref().unwrap().to_account_info(), // Source
                ctx.accounts.creator.to_account_info(), // Seller
                &ctx.remaining_accounts, // Royalty creators
                ctx.accounts.system_program.to_account_info(),
                Some(&[bid_account_seeds]), // Bid PDA is signing
                sale_price,
                royalty_bps,
                config.platform_fee_bps,
                config.max_royalty_subsidy_bps,
                // Subsidy logic
                &ctx.accounts.quest_program,
                &ctx.accounts.program_authority,
                config.program_authority_bump,
            )?;

            // 2. Transfer NFT to winner
            // ... (Same as before) ...
            token::transfer(
                CpiContext::new_with_signer(
                    ctx.accounts.token_program.to_account_info(),
                    Transfer {
                        from: ctx.accounts.nft_vault.to_account_info(),
                        to: ctx.accounts.winner_token_account.to_account_info(),
                        authority: ctx.accounts.nft_vault.to_account_info(),
                    },
                    &[vault_signer_seeds],
                ),
                1,
            )?;

            // 3. CPI to Quest Program
            helpers::cpi_update_quest_progress(
                &ctx.accounts.quest_program,
                &ctx.accounts.program_authority,
                &ctx.accounts.quest_user_account,
                &ctx.accounts.winner,
                &ctx.accounts.system_program,
                ctx.accounts.config.program_authority_bump,
                QuestActionType::Buy,
            )?;

            emit!(AuctionFinalized {
                auction_id: auction_key,
                winner: auction.winner,
                final_price: sale_price
            });
            emit!(Sale {
                seller: auction.creator,
                buyer: auction.winner,
                nft_mint: auction.nft_mint,
                price: sale_price
            });
        }
        
        // --- 4. Close the NFT vault ---
        // ... (Same as before) ...
        token::close_account(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                CloseAccount {
                    account: ctx.accounts.nft_vault.to_account_info(),
                    destination: ctx.accounts.creator.to_account_info(),
                    authority: ctx.accounts.nft_vault.to_account_info(),
                },
                &[vault_signer_seeds],
            )
        )?;
        Ok(())
    }

    pub fn cancel_auction(ctx: Context<CancelAuction>) -> Result<()> {
        // ... (Same as before: validate no bids, return NFT, close vault) ...
        let auction = &ctx.accounts.auction_account;
        if auction.current_bid != 0 { return err!(MarketplaceError::AuctionHasBids); }
        auction.status = AuctionStatus::Cancelled;
        let vault_signer_seeds = &[
            AUCTION_VAULT_SEED,
            auction.key().as_ref(),
            &[ctx.bumps.nft_vault],
        ];

        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.nft_vault.to_account_info(),
                    to: ctx.accounts.creator_token_account.to_account_info(),
                    authority: ctx.accounts.nft_vault.to_account_info(),
                },
                &[vault_signer_seeds],
            ),
            1,
        )?;
        token::close_account(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                CloseAccount {
                    account: ctx.accounts.nft_vault.to_account_info(),
                    destination: ctx.accounts.creator.to_account_info(),
                    authority: ctx.accounts.nft_vault.to_account_info(),
                },
                &[vault_signer_seeds],
            )
        )?;
        
        emit!(AuctionCancelled { auction_id: auction.key() });
        Ok(())
    }
}

// --- MODULES ---

mod helpers {
    use super::*;

    #[allow(clippy::too_many_arguments)]
    pub fn handle_payment_and_royalties<'info>(
        config: AccountInfo<'info>, // Not used, just for holding config data
        fee_wallet: AccountInfo<'info>,
        quest_wallet: AccountInfo<'info>,
        vault_wallet: AccountInfo<'info>,
        source_account: AccountInfo<'info>, // Buyer wallet or Bid PDA
        seller: AccountInfo<'info>,
        royalty_creator_wallets: &[AccountInfo<'info>], // Passed as remaining_accounts
        system_program: AccountInfo<'info>,
        source_signer_seeds: Option<&[&[&[u8]]]>, // None if buyer, Some if PDA
        sale_price: u64,
        royalty_bps: u16,
        platform_fee_bps: u16,
        max_royalty_subsidy_bps: u16,
        // For subsidy CPI
        quest_program: &Program<'info, QuestProgram>,
        program_authority: &AccountInfo<'info>,
        program_authority_bump: u8,
    ) -> Result<()> {
        
        // --- 1. Calculate Fees ---
        let total_fee = (sale_price * platform_fee_bps as u64) / 10_000;
        let fee_wallet_amount = total_fee / 2; // 50%
        let quest_wallet_amount = (total_fee * 3) / 10; // 30%
        let vault_wallet_amount = total_fee - fee_wallet_amount - quest_wallet_amount; // 20%
        
        // --- 2. Calculate Royalties & Subsidy ---
        let total_royalty = (sale_price * royalty_bps as u64) / 10_000;
        let mut seller_royalty_deduction = total_royalty;
        let mut subsidy_to_pay = 0;

        // Check for active subsidy event
        let event_is_active = false; // TODO: Pass Event PDA to check this
        
        if event_is_active {
            let subsidy_bps = min(royalty_bps, max_royalty_subsidy_bps);
            subsidy_to_pay = (sale_price * subsidy_bps as u64) / 10_000;
            seller_royalty_deduction = total_royalty - subsidy_to_pay;
        }

        // --- 3. Calculate Final Seller Proceeds ---
        let seller_proceeds = sale_price
            .checked_sub(total_fee)
            .ok_or(MarketplaceError::MathOverflow)?
            .checked_sub(seller_royalty_deduction)
            .ok_or(MarketplaceError::MathOverflow)?;

        // --- 4. Perform Transfers ---
        
        // A. Pay 3-way Fee Split
        transfer_sol(&source_account, &fee_wallet, fee_wallet_amount, &system_program, source_signer_seeds)?;
        transfer_sol(&source_account, &quest_wallet, quest_wallet_amount, &system_program, source_signer_seeds)?;
        transfer_sol(&source_account, &vault_wallet, vault_wallet_amount, &system_program, source_signer_seeds)?;

        // B. Pay Seller Proceeds
        transfer_sol(&source_account, &seller, seller_proceeds, &system_program, source_signer_seeds)?;
        
        // C. Pay Royalties (from seller deduction)
        if seller_royalty_deduction > 0 && !royalty_creator_wallets.is_empty() {
            let royalty_per_creator = seller_royalty_deduction / (royalty_creator_wallets.len() as u64);
            for creator_wallet in royalty_creator_wallets {
                transfer_sol(&source_account, creator_wallet, royalty_per_creator, &system_program, source_signer_seeds)?;
            }
        }
        
        // D. Pay Subsidy (from quest wallet via CPI)
        if subsidy_to_pay > 0 && !royalty_creator_wallets.is_empty() {
            let subsidy_per_creator = subsidy_to_pay / (royalty_creator_wallets.len() as u64);
            let authority_seeds = &[
                PROGRAM_AUTHORITY_SEED,
                &[program_authority_bump],
            ];
            let signer_seeds = &[&authority_seeds[..]];

            for creator_wallet in royalty_creator_wallets {
                let cpi_program = quest_program.to_account_info();
                let cpi_accounts = quest_program::cpi::accounts::PayRoyaltySubsidy {
                    quest_wallet: quest_wallet.to_account_info(),
                    creator: creator_wallet.to_account_info(),
                    program_authority: program_authority.to_account_info(),
                    system_program: system_program.to_account_info(),
                };
                quest_program::cpi::pay_royalty_subsidy(
                    CpiContext::new_with_signer(cpi_program, cpi_accounts, signer_seeds),
                    subsidy_per_creator
                )?;
            }
        }

        Ok(())
    }

    // Abstraction for a single SOL transfer
    pub fn transfer_sol<'info>(
        from: &AccountInfo<'info>,
        to: &AccountInfo<'info>,
        amount: u64,
        system_program: &AccountInfo<'info>,
        signer_seeds: Option<&[&[&[u8]]]>,
    ) -> Result<()> {
        if amount == 0 { return Ok(()); }
        let transfer_ix = system_instruction::transfer(from.key, to.key, amount);
        let accounts = &[from.clone(), to.clone(), system_program.clone()];
        match signer_seeds {
            Some(seeds) => anchor_lang::solana_program::program::invoke_signed(&transfer_ix, accounts, seeds)?,
            None => anchor_lang::solana_program::program::invoke(&transfer_ix, accounts)?,
        }
        Ok(())
    }

    // Helper to CPI to the Quest Program
    #[allow(clippy::too_many_arguments)]
    pub fn cpi_update_quest_progress<'info>(
        quest_program: &Program<'info, QuestProgram>,
        program_authority: &AccountInfo<'info>,
        quest_user_account: &AccountInfo<'info>,
        user: &AccountInfo<'info>,
        system_program: &AccountInfo<'info>,
        program_authority_bump: u8,
        action_type: QuestActionType,
    ) -> Result<()> {
        let cpi_program = quest_program.to_account_info();
        let cpi_accounts = UpdateProgress {
            quest_user_account: quest_user_account.to_account_info(),
            user: user.to_account_info(),
            program_authority: program_authority.to_account_info(),
            system_program: system_program.to_account_info(),
        };

        let authority_seeds = &[
            PROGRAM_AUTHORITY_SEED,
            &[program_authority_bump],
        ];
        let signer_seeds = &[&authority_seeds[..]];

        quest_program::cpi::update_progress(
            CpiContext::new_with_signer(cpi_program, cpi_accounts, signer_seeds),
            action_type
        )?;

        Ok(())
    }
}

// --- CONSTANTS ---
const CONFIG_SEED: &[u8] = b"config";
const PROGRAM_AUTHORITY_SEED: &[u8] = b"authority";
const LISTING_SEED: &[u8] = b"listing";
const VAULT_SEED: &[u8] = b"vault";
const BID_SEED: &[u8] = b"bid";
const AUCTION_SEED: &[u8] = b"auction";
const AUCTION_VAULT_SEED: &[u8] = b"auction_vault";
const AUCTION_BID_SEED: &[u8] = b"auction_bid";


// --- ENUMS ---
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum ListingType { None, DirectSell, SellIntent }
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum BidStatus { Active, Accepted, Rejected, Cancelled, Expired }
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum AuctionStatus { Active, Completed, Cancelled }

// --- ACCOUNT STRUCTS ---

#[account]
#[derive(Default)]
pub struct MarketplaceConfig {
    pub admin: Pubkey,
    pub fee_wallet: Pubkey,
    pub quest_wallet: Pubkey, // This is just an address, the Quest Program owns the PDA
    pub vault_wallet: Pubkey,
    pub quest_program: Pubkey,
    pub program_authority_bump: u8,
    pub platform_fee_bps: u16,
    pub max_royalty_subsidy_bps: u16,
    pub min_vitality_for_rebate: u8,
    pub rebate_counter_min: u8,
    pub auction_loser_rebate_lamports: u64,
}

#[account]
pub struct ListingAccount {
    pub seller: Pubkey,
    pub nft_mint: Pubkey,
    pub price_lamports: u64,
    pub list_type: ListingType,
    pub bump: u8,
}

#[account]
pub struct PrivateBidAccount {
    pub bidder: Pubkey,
    pub nft_mint: Pubkey,
    pub owner_at_creation: Pubkey,
    pub amount_lamports: u64,
    pub expires_at: i64,
    pub status: BidStatus,
    pub is_rebate_eligible: bool,
    pub negotiation_count: u8,
    pub bump: u8,
}

#[account]
pub struct AuctionAccount {
    pub creator: Pubkey,
    pub nft_mint: Pubkey,
    pub end_time: i64,
    pub starting_price: u64,
    pub current_bid: u64,
    pub current_bidder: Pubkey,
    pub final_price: u64,
    pub winner: Pubkey,
    pub status: AuctionStatus,
    pub bump: u8,
}

#[account]
pub struct AuctionBidAccount {
    pub bidder: Pubkey,
    pub amount: u64,
    pub bump: u8,
}

// --- CONTEXTS ---
// (Only showing modified contexts)

#[derive(Accounts)]
pub struct InitializeConfig<'info> {
    #[account(
        init,
        payer = admin,
        space = 8 + 203, // 8 + MarketplaceConfig size
        seeds = [CONFIG_SEED],
        bump
    )]
    pub config: Account<'info, MarketplaceConfig>,
    
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump
    )]
    /// CHECK: This is a PDA used for signing CPIs
    pub program_authority: AccountInfo<'info>,

    #[account(mut)]
    pub admin: Signer<'info>,
    
    /// CHECK: Wallet address
    pub fee_wallet: AccountInfo<'info>,
    /// CHECK: Wallet address
    pub quest_wallet: AccountInfo<'info>,
    /// CHECK: Wallet address
    pub vault_wallet: AccountInfo<'info>,
    /// CHECK: Executable program
    pub quest_program: AccountInfo<'info>,
    
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct UpdateConfig<'info> {
    #[account(
        mut,
        seeds = [CONFIG_SEED],
        bump,
        has_one = admin
    )]
    pub config: Account<'info, MarketplaceConfig>,
    pub admin: Signer<'info>,
}

#[derive(Accounts)]
pub struct ListNft<'info> {
    #[account(mut)]
    pub seller: Signer<'info>,
    // ... listing_account, nft_vault, nft_mint, seller_token_account
    #[account(
        init,
        payer = seller,
        space = 8 + 74,
        seeds = [LISTING_SEED, seller.key().as_ref(), nft_mint.key().as_ref()],
        bump
    )]
    pub listing_account: Account<'info, ListingAccount>,
    #[account(
        init,
        payer = seller,
        seeds = [VAULT_SEED, listing_account.key().as_ref()],
        bump,
        token::mint = nft_mint,
        token::authority = listing_account,
    )]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = seller)]
    pub seller_token_account: Account<'info, TokenAccount>,
    
    // --- Quest CPI Accounts ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    #[account(mut)]
    /// CHECK: Account is validated by the Quest Program
    pub quest_user_account: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,
    
    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct UnlistNft<'info> {
    // ... (Same as before) ...
    #[account(mut)]
    pub seller: Signer<'info>,
    #[account(
        mut,
        close = seller,
        seeds = [LISTING_SEED, seller.key().as_ref(), nft_mint.key().as_ref()],
        bump = listing_account.bump,
        has_one = seller, has_one = nft_mint
    )]
    pub listing_account: Account<'info, ListingAccount>,
    #[account(mut, seeds = [VAULT_SEED, listing_account.key().as_ref()], bump)]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = seller)]
    pub seller_token_account: Account<'info, TokenAccount>,
    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
}

#[derive(Accounts)]
pub struct BuyListedNft<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(mut)]
    /// CHECK: Seller wallet
    pub seller: AccountInfo<'info>,
    // ... listing_account, nft_vault, nft_mint, buyer_token_account
    #[account(
        mut,
        close = seller,
        seeds = [LISTING_SEED, seller.key().as_ref(), nft_mint.key().as_ref()],
        bump = listing_account.bump,
        has_one = seller, has_one = nft_mint
    )]
    pub listing_account: Account<'info, ListingAccount>,
    #[account(mut, seeds = [VAULT_SEED, listing_account.key().as_ref()], bump)]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(
        init_if_needed,
        payer = buyer,
        associated_token::mint = nft_mint,
        associated_token::authority = buyer
    )]
    pub buyer_token_account: Account<'info, TokenAccount>,
    
    // --- Config & Wallets ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(mut, address = config.fee_wallet)]
    /// CHECK: Address validated by config
    pub fee_wallet: AccountInfo<'info>,
    #[account(mut, address = config.quest_wallet)]
    /// CHECK: Address validated by config
    pub quest_wallet: AccountInfo<'info>,
    #[account(mut, address = config.vault_wallet)]
    /// CHECK: Address validated by config
    pub vault_wallet: AccountInfo<'info>,

    // --- Quest CPI Accounts ---
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    #[account(mut)]
    /// CHECK: Account is validated by the Quest Program
    pub quest_user_account: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,

    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, anchor_spl::associated_token::AssociatedToken>,
    pub rent: Sysvar<'info, Rent>,
    // Pass royalty_creator_wallets as remaining_accounts
}

#[derive(Accounts)]
pub struct PlacePrivateBid<'info> {
    #[account(mut)]
    pub bidder: Signer<'info>,
    // ... bid_account, nft_mint, nft_owner_token_account, nft_owner
    #[account(
        init,
        payer = bidder,
        space = 8 + 124,
        seeds = [BID_SEED, bidder.key().as_ref(), nft_mint.key().as_ref()],
        bump
    )]
    pub bid_account: Account<'info, PrivateBidAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(
        owner = token::ID,
        constraint = nft_owner_token_account.mint == nft_mint.key(),
        constraint = nft_owner_token_account.amount == 1
    )]
    pub nft_owner_token_account: Account<'info, TokenAccount>,
    #[account(owner = system_program::ID, address = nft_owner_token_account.owner)]
    /// CHECK: We just need the owner's key.
    pub nft_owner: AccountInfo<'info>,

    // --- Quest CPI Accounts ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    #[account(mut)]
    /// CHECK: Account is validated by the Quest Program
    pub quest_user_account: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,
    
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct ManagePrivateBid<'info> {
    // ... (Same as before) ...
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(
        mut,
        close = bidder,
        seeds = [BID_SEED, bidder.key().as_ref(), nft_mint.key().as_ref()],
        bump = bid_account.bump,
        has_one = nft_mint,
        constraint = bid_account.bidder == signer.key() || bid_account.owner_at_creation == signer.key()
    )]
    pub bid_account: Account<'info, PrivateBidAccount>,
    #[account(mut)]
    /// CHECK: This is the bidder, who gets the refund.
    pub bidder: AccountInfo<'info>,
    /// CHECK: This is just to build the seed
    pub nft_mint: AccountInfo<'info>,
}

#[derive(Accounts)]
pub struct AcceptPrivateBid<'info> {
    #[account(mut)]
    pub seller: Signer<'info>,
    #[account(mut)]
    /// CHECK: Bidder wallet
    pub bidder: AccountInfo<'info>,
    // ... bid_account, nft_mint, seller_token_account, bidder_token_account
    #[account(
        mut,
        close = seller,
        seeds = [BID_SEED, bidder.key().as_ref(), nft_mint.key().as_ref()],
        bump = bid_account.bump,
        has_one = nft_mint,
        constraint = bid_account.owner_at_creation == seller.key()
    )]
    pub bid_account: Account<'info, PrivateBidAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = seller)]
    pub seller_token_account: Account<'info, TokenAccount>,
    #[account(
        init_if_needed,
        payer = seller,
        associated_token::mint = nft_mint,
        associated_token::authority = bidder
    )]
    pub bidder_token_account: Account<'info, TokenAccount>,
    
    // --- Config & Wallets ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(mut, address = config.fee_wallet)]
    /// CHECK: Address validated by config
    pub fee_wallet: AccountInfo<'info>,
    #[account(mut, address = config.quest_wallet)]
    /// CHECK: Address validated by config
    pub quest_wallet: AccountInfo<'info>,
    #[account(mut, address = config.vault_wallet)]
    /// CHECK: Address validated by config
    pub vault_wallet: AccountInfo<'info>,
    
    // --- Quest CPI Accounts ---
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    #[account(mut)]
    /// CHECK: Account is validated by the Quest Program
    pub quest_user_account: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,
    
    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, anchor_spl::associated_token::AssociatedToken>,
    pub rent: Sysvar<'info, Rent>,
    // Pass royalty_creator_wallets as remaining_accounts
}

#[derive(Accounts)]
pub struct CreateAuction<'info> {
    // ... (Same as before) ...
    #[account(mut)]
    pub creator: Signer<'info>,
    #[account(
        init,
        payer = creator,
        space = 8 + 169,
        seeds = [AUCTION_SEED, creator.key().as_ref(), nft_mint.key().as_ref()],
        bump
    )]
    pub auction_account: Account<'info, AuctionAccount>,
    #[account(
        init,
        payer = creator,
        seeds = [AUCTION_VAULT_SEED, auction_account.key().as_ref()],
        bump,
        token::mint = nft_mint,
        token::authority = nft_vault,
    )]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = creator)]
    pub creator_token_account: Account<'info, TokenAccount>,
    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct PlaceAuctionBid<'info> {
    #[account(mut)]
    pub bidder: Signer<'info>,
    #[account(
        mut,
        seeds = [AUCTION_SEED, auction_account.creator.as_ref(), auction_account.nft_mint.as_ref()],
        bump = auction_account.bump
    )]
    pub auction_account: Account<'info, AuctionAccount>,
    #[account(
        init,
        payer = bidder,
        space = 8 + 41,
        seeds = [AUCTION_BID_SEED, auction_account.key().as_ref(), bidder.key().as_ref()],
        bump
    )]
    pub new_bid_account: Account<'info, AuctionBidAccount>,
    #[account(
        mut,
        seeds = [AUCTION_BID_SEED, auction_account.key().as_ref(), previous_bidder.key().as_ref()],
        bump = previous_bid_account.bump,
        close = previous_bidder
    )]
    pub previous_bid_account: Option<Account<'info, AuctionBidAccount>>,
    #[account(mut)]
    /// CHECK: The previous bidder, who gets a refund and rebate.
    pub previous_bidder: AccountInfo<'info>,

    // --- Config & CPI Accounts ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(mut, address = config.quest_wallet)]
    /// CHECK: Address validated by config
    pub quest_wallet: AccountInfo<'info>,
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,
    
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct FinalizeAuction<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut)]
    /// CHECK: Creator wallet
    pub creator: AccountInfo<'info>,
    #[account(
        mut,
        close = creator,
        seeds = [AUCTION_SEED, creator.key().as_ref(), nft_mint.key().as_ref()],
        bump = auction_account.bump,
        has_one = creator, has_one = nft_mint
    )]
    pub auction_account: Account<'info, AuctionAccount>,
    #[account(mut, seeds = [AUCTION_VAULT_SEED, auction_account.key().as_ref()], bump)]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = creator)]
    pub creator_token_account: Account<'info, TokenAccount>,
    #[account(
        mut,
        seeds = [AUCTION_BID_SEED, auction_account.key().as_ref(), winner.key().as_ref()],
        bump = highest_bid_account.bump,
        close = creator
    )]
    pub highest_bid_account: Option<Account<'info, AuctionBidAccount>>,
    #[account(mut)]
    /// CHECK: This is the winner.
    pub winner: AccountInfo<'info>,
    #[account(
        init_if_needed,
        payer = signer,
        associated_token::mint = nft_mint,
        associated_token::authority = winner
    )]
    pub winner_token_account: Account<'info, TokenAccount>,
    
    // --- Config & Wallets ---
    #[account(seeds = [CONFIG_SEED], bump)]
    pub config: Account<'info, MarketplaceConfig>,
    #[account(mut, address = config.fee_wallet)]
    /// CHECK: Address validated by config
    pub fee_wallet: AccountInfo<'info>,
    #[account(mut, address = config.quest_wallet)]
    /// CHECK: Address validated by config
    pub quest_wallet: AccountInfo<'info>,
    #[account(mut, address = config.vault_wallet)]
    /// CHECK: Address validated by config
    pub vault_wallet: AccountInfo<'info>,

    // --- Quest CPI Accounts ---
    #[account(
        seeds = [PROGRAM_AUTHORITY_SEED],
        bump = config.program_authority_bump
    )]
    /// CHECK: PDA Signer
    pub program_authority: AccountInfo<'info>,
    #[account(mut)]
    /// CHECK: Account is validated by the Quest Program
    pub quest_user_account: AccountInfo<'info>,
    pub quest_program: Program<'info, QuestProgram>,

    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, anchor_spl::associated_token::AssociatedToken>,
    pub rent: Sysvar<'info, Rent>,
    // Pass royalty_creator_wallets as remaining_accounts
}

#[derive(Accounts)]
pub struct CancelAuction<'info> {
    // ... (Same as before) ...
    #[account(mut)]
    pub creator: Signer<'info>,
    #[account(
        mut,
        close = creator,
        seeds = [AUCTION_SEED, creator.key().as_ref(), nft_mint.key().as_ref()],
        bump = auction_account.bump,
        has_one = creator, has_one = nft_mint
    )]
    pub auction_account: Account<'info, AuctionAccount>,
    #[account(mut, seeds = [AUCTION_VAULT_SEED, auction_account.key().as_ref()], bump)]
    pub nft_vault: Account<'info, TokenAccount>,
    pub nft_mint: Account<'info, Mint>,
    #[account(mut, associated_token::mint = nft_mint, associated_token::authority = creator)]
    pub creator_token_account: Account<'info, TokenAccount>,
    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
}


// --- EVENTS ---
#[event]
pub struct Listed { seller: Pubkey, nft_mint: Pubkey, price: u64, list_type: ListingType }
#[event]
pub struct Unlisted { seller: Pubkey, nft_mint: Pubkey }
#[event]
pub struct Sale { seller: Pubkey, buyer: Pubkey, nft_mint: Pubkey, price: u64 }
#[event]
pub struct BidPlaced { bid_id: Pubkey, bidder: Pubkey, nft_mint: Pubkey, amount: u64 }
#[event]
pub struct BidAccepted { bid_id: Pubkey }
#[event]
pub struct BidRejected { bid_id: Pubkey }
#[event]
pub struct BidCancelled { bid_id: Pubkey }
#[event]
pub struct AuctionCreated { auction_id: Pubkey, creator: Pubkey, nft_mint: Pubkey, ends_at: i64 }
#[event]
pub struct AuctionBid { auction_id: Pubkey, bidder: Pubkey, amount: u64 }
#[event]
pub struct AuctionFinalized { auction_id: Pubkey, winner: Pubkey, final_price: u64 }
#[event]
pub struct AuctionCancelled { auction_id: Pubkey }

// --- ERRORS ---
#[error_code]
pub enum MarketplaceError {
    #[msg("Price must be greater than zero.")]
    InvalidPrice,
    #[msg("The owner of an NFT cannot buy or bid on it.")]
    OwnerCannotBuy,
    #[msg("This bid is not active.")]
    BidNotActive,
    #[msg("This bid has expired.")]
    BidExpired,
    #[msg("This auction is not active.")]
    AuctionNotActive,
    #[msg("This auction has not ended yet.")]
    AuctionNotEnded,
    #[msg("This auction has already ended.")]
    AuctionEnded,
    #[msg("Cannot cancel an auction that has bids.")]
    AuctionHasBids,
    #[msg("Bid amount must be higher than the current highest bid.")]
    BidTooLow,
    #[msg("A math operation resulted in an overflow.")]
    MathOverflow,
}