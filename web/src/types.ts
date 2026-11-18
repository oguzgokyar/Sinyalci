export interface SystemState {
  kill_switch: boolean;
  dry_run: boolean;
  webhook_secret: string;
  total_balance: number;
  active_devices: number;
  total_devices: number;
  today_orders: number;
  pending_orders: number;
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
