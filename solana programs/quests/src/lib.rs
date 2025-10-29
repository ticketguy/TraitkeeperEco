// --- quests/src/lib.rs ---

use anchor_lang::prelude::*;
use anchor_lang::solana_program::{system_instruction};

declare_id!(" QUEST_PROGRAM_ID_HERE ");

#[program]
pub mod quest_program {
    use super::*;

    // --- 1. ADMIN INSTRUCTIONS ---
    // (Called by your admin panel)

    pub fn initialize_quest_config(
        ctx: Context<InitializeQuestConfig>,
        marketplace_admin: Pubkey,
    ) -> Result<()> {
        let config = &mut ctx.accounts.quest_config;
        config.admin = marketplace_admin;
        
        let wallet = &mut ctx.accounts.quest_wallet;
        wallet.bump = ctx.bumps.quest_wallet;

        Ok(())
    }
    
    pub fn update_quest_admin(ctx: Context<UpdateQuestConfig>, new_admin: Pubkey) -> Result<()> {
        ctx.accounts.quest_config.admin = new_admin;
        Ok(())
    }
    
    pub fn create_quest(
        ctx: Context<CreateQuest>,
        quest_id: u64,
        action_type: QuestActionType,
        target_count: u32,
        reward_lamports: u64,
    ) -> Result<()> {
        let quest = &mut ctx.accounts.quest_config;
        quest.admin = *ctx.accounts.admin.key;
        quest.quest_id = quest_id;
        quest.action_type = action_type;
        quest.target_count = target_count;
        quest.reward_lamports = reward_lamports;
        quest.is_active = true;
        quest.bump = ctx.bumps.quest_config;
        Ok(())
    }
    
    pub fn toggle_quest_active(ctx: Context<ManageQuest>, is_active: bool) -> Result<()> {
        ctx.accounts.quest_config.is_active = is_active;
        Ok(())
    }

    // --- 2. USER INSTRUCTION ---
    // (Called by the user to claim)

    pub fn claim_quest_reward(ctx: Context<ClaimQuestReward>) -> Result<()> {
        let user_account = &mut ctx.accounts.quest_user_account;
        let quest = &ctx.accounts.quest_config;

        if !quest.is_active {
            return err!(QuestError::QuestNotActive);
        }

        if user_account.claimed_quests.contains(&quest.quest_id) {
            return err!(QuestError::QuestAlreadyClaimed);
        }
        
        let has_progress = match quest.action_type {
            QuestActionType::Buy => user_account.nfts_bought >= quest.target_count,
            QuestActionType::Bid => user_account.bids_placed >= quest.target_count,
            QuestActionType::List => user_account.nfts_listed >= quest.target_count,
        };

        if !has_progress {
            return err!(QuestError::QuestNotCompleted);
        }

        // Pay reward from quest wallet
        let seeds = &[QUEST_WALLET_SEED, &[ctx.accounts.quest_wallet.bump]];
        let signer_seeds = &[&seeds[..]];

        let transfer_ix = system_instruction::transfer(
            ctx.accounts.quest_wallet.to_account_info().key,
            ctx.accounts.user.key,
            quest.reward_lamports,
        );
        anchor_lang::solana_program::program::invoke_signed(
            &transfer_ix,
            &[
                ctx.accounts.quest_wallet.to_account_info(),
                ctx.accounts.user.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            signer_seeds,
        )?;

        // Mark as claimed
        user_account.claimed_quests.push(quest.quest_id);

        emit!(QuestClaimed {
            user: *ctx.accounts.user.key,
            quest_id: quest.quest_id,
            reward: quest.reward_lamports
        });
        
        Ok(())
    }

    // --- 3. CPI-ONLY INSTRUCTIONS ---
    // (Called ONLY by the Marketplace Program)

    pub fn update_progress(
        ctx: Context<UpdateProgress>,
        action_type: QuestActionType,
    ) -> Result<()> {
        // Security: This instruction is signed by the Marketplace's
        // ProgramAuthority PDA, so only it can call this.
        
        let user_account = &mut ctx.accounts.quest_user_account;
        
        // Initialize if first time
        if user_account.user == Pubkey::default() {
            user_account.user = *ctx.accounts.user.key;
            user_account.bump = ctx.bumps.quest_user_account;
        }

        match action_type {
            QuestActionType::Buy => user_account.nfts_bought += 1,
            QuestActionType::Bid => user_account.bids_placed += 1,
            QuestActionType::List => user_account.nfts_listed += 1,
        }
        Ok(())
    }

    pub fn pay_auction_loser_rebate(
        ctx: Context<PayAuctionLoserRebate>,
        amount: u64,
    ) -> Result<()> {
        // Security: Signed by Marketplace PDA
        let seeds = &[QUEST_WALLET_SEED, &[ctx.accounts.quest_wallet.bump]];
        let signer_seeds = &[&seeds[..]];

        let transfer_ix = system_instruction::transfer(
            ctx.accounts.quest_wallet.to_account_info().key,
            ctx.accounts.loser_bidder.key,
            amount,
        );
        anchor_lang::solana_program::program::invoke_signed(
            &transfer_ix,
            &[
                ctx.accounts.quest_wallet.to_account_info(),
                ctx.accounts.loser_bidder.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            signer_seeds,
        )?;
        Ok(())
    }
    
    pub fn pay_negotiation_rebate(
        ctx: Context<PayNegotiationRebate>,
        amount: u64,
    ) -> Result<()> {
        // Security: Signed by Marketplace PDA
        let seeds = &[QUEST_WALLET_SEED, &[ctx.accounts.quest_wallet.bump]];
        let signer_seeds = &[&seeds[..]];

        let transfer_ix = system_instruction::transfer(
            ctx.accounts.quest_wallet.to_account_info().key,
            ctx.accounts.bidder.key,
            amount,
        );
        anchor_lang::solana_program::program::invoke_signed(
            &transfer_ix,
            &[
                ctx.accounts.quest_wallet.to_account_info(),
                ctx.accounts.bidder.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            signer_seeds,
        )?;
        Ok(())
    }
    
    pub fn pay_royalty_subsidy(
        ctx: Context<PayRoyaltySubsidy>,
        amount: u64,
    ) -> Result<()> {
        // Security: Signed by Marketplace PDA
        let seeds = &[QUEST_WALLET_SEED, &[ctx.accounts.quest_wallet.bump]];
        let signer_seeds = &[&seeds[..]];

        let transfer_ix = system_instruction::transfer(
            ctx.accounts.quest_wallet.to_account_info().key,
            ctx.accounts.creator.key,
            amount,
        );
        anchor_lang::solana_program::program::invoke_signed(
            &transfer_ix,
            &[
                ctx.accounts.quest_wallet.to_account_info(),
                ctx.accounts.creator.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            signer_seeds,
        )?;
        Ok(())
    }
}

// --- CONSTANTS ---
const QUEST_CONFIG_SEED: &[u8] = b"quest_config";
const GLOBAL_CONFIG_SEED: &[u8] = b"global_quest_config";
const QUEST_USER_SEED: &[u8] = b"quest_user";
const QUEST_WALLET_SEED: &[u8] = b"quest_wallet";

// --- ENUMS ---
#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum QuestActionType {
    Buy,
    Bid,
    List,
}

// --- ACCOUNT STRUCTS ---

#[account]
pub struct QuestGlobalConfig {
    pub admin: Pubkey,
}

#[account]
pub struct QuestWallet {
    pub bump: u8,
}

#[account]
pub struct QuestConfig {
    pub admin: Pubkey,
    pub quest_id: u64,
    pub action_type: QuestActionType,
    pub target_count: u32,
    pub reward_lamports: u64,
    pub is_active: bool,
    pub bump: u8,
}

#[account]
#[derive(Default)]
pub struct QuestUserAccount {
    pub user: Pubkey,
    pub nfts_bought: u32,
    pub bids_placed: u32,
    pub nfts_listed: u32,
    // Allows for ~100 claimed quests
    pub claimed_quests: Vec<u64>, 
    pub bump: u8,
}

// --- CONTEXTS ---

#[derive(Accounts)]
pub struct InitializeQuestConfig<'info> {
    #[account(
        init,
        payer = admin,
        space = 8 + 32, // 8 + QuestGlobalConfig size
        seeds = [GLOBAL_CONFIG_SEED],
        bump
    )]
    pub quest_config: Account<'info, QuestGlobalConfig>,
    
    #[account(
        init,
        payer = admin,
        space = 8 + 1, // 8 + QuestWallet size
        seeds = [QUEST_WALLET_SEED],
        bump
    )]
    pub quest_wallet: Account<'info, QuestWallet>,

    #[account(mut)]
    pub admin: Signer<'info>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct UpdateQuestConfig<'info> {
    #[account(
        mut,
        seeds = [GLOBAL_CONFIG_SEED],
        bump,
        has_one = admin
    )]
    pub quest_config: Account<'info, QuestGlobalConfig>,
    pub admin: Signer<'info>,
}


#[derive(Accounts)]
#[instruction(quest_id: u64)]
pub struct CreateQuest<'info> {
    #[account(
        init,
        payer = admin,
        space = 8 + 65, // 8 + QuestConfig size
        seeds = [QUEST_CONFIG_SEED, &quest_id.to_le_bytes()],
        bump
    )]
    pub quest_config: Account<'info, QuestConfig>,
    
    #[account(seeds = [GLOBAL_CONFIG_SEED], bump, has_one = admin)]
    pub global_config: Account<'info, QuestGlobalConfig>,
    
    #[account(mut)]
    pub admin: Signer<'info>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct ManageQuest<'info> {
    #[account(
        mut,
        has_one = admin,
        seeds = [QUEST_CONFIG_SEED, &quest_config.quest_id.to_le_bytes()],
        bump = quest_config.bump
    )]
    pub quest_config: Account<'info, QuestConfig>,
    
    #[account(seeds = [GLOBAL_CONFIG_SEED], bump, has_one = admin)]
    pub global_config: Account<'info, QuestGlobalConfig>,

    pub admin: Signer<'info>,
}

#[derive(Accounts)]
pub struct ClaimQuestReward<'info> {
    #[account(mut)]
    pub user: Signer<'info>,
    
    #[account(
        seeds = [QUEST_CONFIG_SEED, &quest_config.quest_id.to_le_bytes()],
        bump = quest_config.bump
    )]
    pub quest_config: Account<'info, QuestConfig>,

    #[account(
        mut,
        seeds = [QUEST_USER_SEED, user.key().as_ref()],
        bump = quest_user_account.bump,
        has_one = user
    )]
    pub quest_user_account: Account<'info, QuestUserAccount>,

    #[account(
        mut,
        seeds = [QUEST_WALLET_SEED], 
        bump = quest_wallet.bump
    )]
    pub quest_wallet: Account<'info, QuestWallet>,

    pub system_program: Program<'info, System>,
}

// --- CPI CONTEXTS ---

#[derive(Accounts)]
pub struct UpdateProgress<'info> {
    #[account(
        init_if_needed,
        payer = program_authority, // Marketplace PDA pays for init
        space = 8 + 857, // 8 + QuestUserAccount size
        seeds = [QUEST_USER_SEED, user.key().as_ref()],
        bump
    )]
    pub quest_user_account: Account<'info, QuestUserAccount>,
    
    /// CHECK: This is the user PDA is being created for
    pub user: AccountInfo<'info>,
    
    // Security: Only the Marketplace Program's PDA can sign this
    #[account(mut)]
    pub program_authority: Signer<'info>, 
    
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

#[derive(Accounts)]
pub struct PayAuctionLoserRebate<'info> {
    #[account(
        mut,
        seeds = [QUEST_WALLET_SEED], 
        bump = quest_wallet.bump
    )]
    pub quest_wallet: Account<'info, QuestWallet>,
    
    #[account(mut)]
    /// CHECK: Account receiving rebate
    pub loser_bidder: AccountInfo<'info>,
    
    pub program_authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct PayNegotiationRebate<'info> {
    #[account(
        mut,
        seeds = [QUEST_WALLET_SEED], 
        bump = quest_wallet.bump
    )]
    pub quest_wallet: Account<'info, QuestWallet>,
    
    #[account(mut)]
    /// CHECK: Account receiving rebate
    pub bidder: AccountInfo<'info>,
    
    pub program_authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct PayRoyaltySubsidy<'info> {
    #[account(
        mut,
        seeds = [QUEST_WALLET_SEED], 
        bump = quest_wallet.bump
    )]
    pub quest_wallet: Account<'info, QuestWallet>,
    
    #[account(mut)]
    /// CHECK: Account receiving royalty
    pub creator: AccountInfo<'info>,
    
    pub program_authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

// --- EVENTS ---
#[event]
pub struct QuestClaimed {
    user: Pubkey,
    quest_id: u64,
    reward: u64,
}

// --- ERRORS ---
#[error_code]
pub enum QuestError {
    #[msg("This quest is not active.")]
    QuestNotActive,
    #[msg("You have not completed the requirements for this quest.")]
    QuestNotCompleted,
    #[msg("You have already claimed the reward for this quest.")]
    QuestAlreadyClaimed,
}