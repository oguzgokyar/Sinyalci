import type { Account, AuditLog, Device, Order, ScanItem, SystemState } from "./types";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getSystem: () => req<SystemState>("/api/system"),
  setKillSwitch: (active: boolean) => req<SystemState>(`/api/system/kill-switch?active=${active}`, { method: "POST" }),
  setDryRun: (active: boolean) => req<SystemState>(`/api/system/dry-run?active=${active}`, { method: "POST" }),
  getLogs: () => req<AuditLog[]>("/api/logs?limit=100"),

  getDevices: () => req<Device[]>("/api/devices"),
  scanDevices: () => req<ScanItem[]>("/api/devices/scan", { method: "POST" }),
  addDevice: (body: { name: string; serial?: string | null; usb_vid: string; usb_pid: string }) =>
    req<Device>("/api/devices", { method: "POST", body: JSON.stringify(body) }),
  deleteDevice: (id: number) => req<{ deleted: boolean }>(`/api/devices/${id}`, { method: "DELETE" }),
  testAoa: (id: number) => req<{ status: string; mode?: string; aoa_version: number }>(`/api/devices/${id}/test-aoa`, { method: "POST" }),
  calibrate: (id: number, key: string, x: number, y: number) =>
    req(`/api/devices/${id}/calibrate`, { method: "POST", body: JSON.stringify({ key, x, y }) }),

  getAccounts: () => req<Account[]>("/api/accounts"),
  syncBalance: (id: number) => req<Account>(`/api/accounts/${id}/sync-balance`, { method: "POST" }),
  addAccount: (body: {
    device_id: number;
    label: string;
    login: string;
    server: string;
    account_type: "Demo" | "Real";
    balance: number;
    max_lot: number;
    daily_max_orders: number;
  }) => req<Account>("/api/accounts", { method: "POST", body: JSON.stringify(body) }),
  toggleAccount: (id: number, enabled: boolean) =>
    req<Account>(`/api/accounts/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  deleteAccount: (id: number) => req<{ deleted: boolean }>(`/api/accounts/${id}`, { method: "DELETE" }),

  getOrders: () => req<Order[]>("/api/orders?limit=100"),
  createOrder: (body: {
    account_ids: number[];
    symbol: string;
    side: "BUY" | "SELL";
    lot: number;
    sl?: number | null;
    tp?: number | null;
    scheduled_at?: string | null;
  }) => req<Order[]>("/api/orders", { method: "POST", body: JSON.stringify(body) }),
  cancelOrder: (id: number) => req<Order>(`/api/orders/${id}/cancel`, { method: "POST" }),
};

export function connectWS(onEvent: (event: string, data: unknown) => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      onEvent(msg.event, msg.data);
    } catch {
      // ignore malformed messages
    }
  };
  return () => ws.close();
}
