/**
 * useRewards — Phase 7 SKELETON hook for the rewards ledger.
 *
 * TODO(adconnect-phase-7): wire to GET /api/rewards (ledger query, scoped to
 *   the distributor) and POST /api/rewards/redeem (redemption event). The
 *   ledger row shape mirrors `Reward` in @/types — backed by
 *   `adconnect.recompensas_acumuladas` per PROJECT.md §5.2.
 */
import type { Reward } from "@/types";

const MOCK_REWARDS: Reward[] = [];

export interface UseRewardsResult {
  data: Reward[];
  totalAccrued: number;
  totalAvailable: number;
  isLoading: boolean;
  error: Error | null;
}

export function useRewards(): UseRewardsResult {
  // TODO(adconnect-phase-7): wire to /api/rewards
  const totalAccrued = MOCK_REWARDS.reduce((sum, r) => sum + r.amount, 0);
  const totalAvailable = MOCK_REWARDS.filter((r) => r.status === "liberado").reduce(
    (sum, r) => sum + r.amount,
    0
  );
  return {
    data: MOCK_REWARDS,
    totalAccrued,
    totalAvailable,
    isLoading: false,
    error: null,
  };
}

export interface RedeemRewardsInput {
  reward_ids: string[];
  apply_to_pedido_id?: string;
}

export interface UseRedeemRewardsResult {
  redeem: (input: RedeemRewardsInput) => void;
  isPending: boolean;
}

export function useRedeemRewards(): UseRedeemRewardsResult {
  // TODO(adconnect-phase-7): wire to POST /api/rewards/redeem
  return {
    redeem: (input) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] redeemRewards", input);
    },
    isPending: false,
  };
}
