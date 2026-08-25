export interface Mandate {
  id: string;
  agent_id?: string;
  status: string;
  budget_usd: number;
  spent_usd: number;
  expires_at: string | null;
  remaining_headroom?: number;
  policy_version?: number | null;
}

export interface LogEvent {
  action: string;
  timestamp: string;
  mandate_id: string;
  details?: string;
  amount?: number;
}

export interface TopMandate {
  id: string;
  spent_usd: number;
}

export interface DashboardStats {
  total_budget: number;
  total_spent: number;
  remaining_headroom: number;
  protected_spend: number;
  requests_blocked: number;
  overspend_prevented: number;
  active_agents: number;
}

export interface PolicySync {
  policy_version: number | null;
  last_synced_at: string | null;
  last_sync_error: string | null;
  control_plane_healthy: boolean;
}

export interface Governance {
  control_plane_configured: boolean;
  local_governance: boolean;
  authoring_mode: string;
}

export type Severity = 'critical' | 'warning' | 'info';

export interface AttentionItem {
  severity: Severity;
  mandate_id: string | null;
  headline: string;
  detail: string;
  suggested_action?: string;
  utilization?: number;
  budget_usd?: number;
  spent_usd?: number;
  remaining_usd?: number;
}

export interface Attention {
  status: 'ok' | 'watch' | 'action_required';
  headline: string;
  subhead: string;
  critical_count: number;
  warning_count: number;
  items: AttentionItem[];
}

export interface BudgetNotice {
  timestamp: string;
  mandate_id: string;
  threshold: number;
  budget_usd: number;
  spent_usd: number;
  projected_exhaustion_at: string | null;
}

export interface DashboardData {
  stats: DashboardStats;
  mandates: Mandate[];
  top_mandates: TopMandate[];
  history: LogEvent[];
  has_expiry?: boolean;
  policy_sync?: PolicySync;
  governance?: Governance;
  attention?: Attention;
  budget_notices?: BudgetNotice[];
}

export const EMPTY_DASHBOARD: DashboardData = {
  stats: {
    total_budget: 0,
    total_spent: 0,
    remaining_headroom: 0,
    protected_spend: 0,
    requests_blocked: 0,
    overspend_prevented: 0,
    active_agents: 0,
  },
  mandates: [],
  top_mandates: [],
  history: [],
  has_expiry: false,
  policy_sync: {
    policy_version: null,
    last_synced_at: null,
    last_sync_error: null,
    control_plane_healthy: false,
  },
  governance: {
    control_plane_configured: false,
    local_governance: true,
    authoring_mode: 'local_ledger',
  },
  attention: undefined,
  budget_notices: [],
};
