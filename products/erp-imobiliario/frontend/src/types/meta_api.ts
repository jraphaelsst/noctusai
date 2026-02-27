export interface MetaConfig {
  id: string;
  org_id: string;
  page_id?: string | null;
  access_token?: string | null;
  ad_account_id?: string | null;
  webhook_verify_token?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MetaLead {
  id: string;
  org_id: string;
  lead_id: string;
  form_id?: string | null;
  form_name?: string | null;
  campo_data: Record<string, string>;
  cliente_id?: string | null;
  importado: boolean;
  importado_em?: string | null;
  created_at: string;
}

export interface MetaCampanha {
  id: string;
  org_id: string;
  campaign_id: string;
  nome?: string | null;
  status?: string | null;
  spend: number;
  impressions: number;
  clicks: number;
  leads: number;
  cpl?: number | null;
  last_sync?: string | null;
  created_at: string;
  updated_at: string;
}
