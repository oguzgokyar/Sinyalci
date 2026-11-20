export interface SystemState {
  kill_switch: boolean;
  dry_run?: boolean;
  webhook_secret: string;
  total_balance: number;
  active_devices: number;
  total_devices: number;
  today_orders: number;
  pending_orders: number;
  env_mode?: string;
  is_docker?: boolean;
  connected_agents?: number;
}

export interface ChecklistItem {
  key: string;
  title: string;
  ok: boolean;
  message: string;
}

export interface EnvironmentInfo {
  env: {
    mode: "local" | "vps";
    is_docker: boolean;
    os: string;
    python_version: string;
    hostname: string;
  };
  env_mode_override: string;
  checklist: ChecklistItem[];
  agent_token: string;
  vps_public_url: string;
  market_data_source?: "biquote" | "yahoo";
  data_poll_interval?: number;
  agents: Array<{
    device_id: string;
    ip: string;
    model: string;
    battery: number | null;
    connected_at: string;
    last_seen: string;
    online: boolean;
  }>;
}

export interface GitHubInfo {
  repo_url: string;
  branch: string;
  has_token: boolean;
  local_git: {
    commit_sha: string;
    short_sha: string;
    branch: string;
    commit_message: string;
    commit_date: string;
    remote_url: string;
  };
}

export interface GitHubCheckResult {
  ok: boolean;
  has_update: boolean;
  local_sha?: string;
  local_short_sha?: string;
  remote_sha?: string;
  remote_short_sha?: string;
  remote_message?: string;
  remote_author?: string;
  remote_date?: string;
  error?: string | null;
}

export interface GitHubPullResult {
  updated: boolean;
  previous_sha: string;
  current_sha: string;
  output: string;
  restart_required: boolean;
}

export interface Device {
  id: number;
  name: string;
  serial: string | null;
  usb_vid: string;
  usb_pid: string;
  screen_width: number;
  screen_height: number;
  profile_path: string;
  status: string;
  battery: number | null;
  aoa_version: number | null;
  created_at: string;
}

export interface ScanItem {
  serial: string | null;
  usb_vid: string | null;
  usb_pid: string | null;
  vendor: string;
  adb_status: string;
  aoa_status: string;
  battery: number | null;
  registered: boolean;
}

export interface Account {
  id: number;
  device_id: number;
  label: string;
  login: string;
  server: string;
  account_type: "Demo" | "Real";
  balance: number;
  max_lot: number;
  daily_max_orders: number;
  daily_max_loss: number;
  enabled: boolean;
  today_orders: number;
  created_at: string;
}

export interface Order {
  id: number;
  account_id: number;
  device_id: number;
  account_label: string;
  symbol: string;
  side: "BUY" | "SELL";
  lot: number;
  sl: number | null;
  tp: number | null;
  status: string;
  scheduled_at: string | null;
  executed_at: string | null;
  latency_ms: number | null;
  ocr_lot: number | null;
  error: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface AuditLog {
  id: number;
  level: string;
  device_id: number | null;
  order_id: number | null;
  message: string;
  created_at: string;
}

export interface AcgSymbol {
  ticker: string;
  name: string;
  category: string;
}

export interface StrategyConfig {
  balance: number;
  risk_percent: number;
  risk_amount: number;
  min_rr: number;
  target_profit: number;
  symbol_suffix: string;
  auto_execute: boolean;
  autopilot_enabled: boolean;
  live_autopilot_enabled?: boolean;
  market_data_source?: "biquote" | "yahoo";
  data_poll_interval?: number;
  last_autopilot_run?: string;
  timeframe: string;
  paper_trading: boolean;
  watchlist: string[];
  favorites: string[];
  acg_symbols: AcgSymbol[];
  max_daily_loss: number;
  tradingagents_url: string;
}

export interface PrescreenCandidate {
  ticker: string;
  price: number;
  rsi: number;
  ema10: number;
  sma50: number;
  setup: "BUY" | "SELL" | "NONE";
  score: number;
  reason: string;
  timeframe: string;
}

export interface StrategySignal {
  id: number;
  ticker: string;
  broker_symbol: string;
  side: "BUY" | "SELL" | "HOLD";
  entry_price: number;
  sl: number;
  tp: number;
  risk_reward: number;
  calculated_lot: number;
  risk_amount: number;
  confidence: number;
  timeframe: string;
  status: "pending" | "executed" | "paper_active" | "rejected" | "expired";
  reasoning: string;
  order_id: number | null;
  created_at: string;
}

export interface PaperPosition {
  id: number;
  signal_id: number | null;
  symbol: string;
  side: "BUY" | "SELL";
  lot: number;
  entry_price: number;
  current_price: number;
  sl: number;
  tp: number;
  risk_amount: number;
  pnl: number;
  status: "open" | "closed_tp" | "closed_sl" | "closed_manual";
  timeframe: string;
  opened_at: string;
  closed_at: string | null;
}

export interface PaperStats {
  open_count: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  realized_pnl: number;
}

export interface SignalStats {
  total: number;
  executed: number;
  pending: number;
}

export interface TradingAgentsHealth {
  healthy: boolean;
  status: string;
  service: string;
  version: string | null;
  latency_ms: number;
  url: string;
  error: string | null;
}

export interface DiagnosticStep {
  step: number;
  title: string;
  ok: boolean;
  duration_ms: number;
  detail: string;
}

export interface DiagnosticResult {
  ok: boolean;
  device_id: number;
  device_name: string;
  total_duration_ms: number;
  steps: DiagnosticStep[];
  message: string;
}

