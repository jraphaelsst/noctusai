/**
 * useSellout — Phase 7 SKELETON hook for sellout reports.
 *
 * TODO(adconnect-phase-7): wire to GET /api/sellout (history) and
 *   POST /api/sellout (submit, polymorphic on submission_mode field per
 *   PROJECT.md §6 Phase 4). NF-e XML upload + freeform attachment go
 *   through Supabase storage SDK on the client; structured-form mode
 *   posts JSON only.
 */
import type {
  SelloutReport,
  SelloutSubmissionMode,
  SelloutLineItem,
} from "@/types";

const MOCK_SELLOUT_HISTORY: SelloutReport[] = [];

export interface UseSelloutHistoryResult {
  data: SelloutReport[];
  isLoading: boolean;
  error: Error | null;
}

export function useSelloutHistory(): UseSelloutHistoryResult {
  // TODO(adconnect-phase-7): wire to /api/sellout
  return {
    data: MOCK_SELLOUT_HISTORY,
    isLoading: false,
    error: null,
  };
}

export interface SubmitSelloutInput {
  submission_mode: SelloutSubmissionMode;
  period_month: string;
  // structured
  line_items?: SelloutLineItem[];
  // nfe_xml
  nfe_file?: File;
  // freeform
  attachment_file?: File;
  notes?: string;
}

export interface UseSubmitSelloutResult {
  submit: (input: SubmitSelloutInput) => void;
  isPending: boolean;
}

export function useSubmitSellout(): UseSubmitSelloutResult {
  // TODO(adconnect-phase-7): wire to POST /api/sellout. For nfe_xml + freeform
  //   modes, upload via Supabase storage first, then POST the resulting URL.
  return {
    submit: (input) => {
      // eslint-disable-next-line no-console
      console.log("[skeleton] submitSellout", input);
    },
    isPending: false,
  };
}
