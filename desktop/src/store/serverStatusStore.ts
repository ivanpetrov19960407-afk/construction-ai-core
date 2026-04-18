import { create } from 'zustand';
import type { HealthResponse } from '../api/coreClient';

export interface ServerStatus {
  isOnline: boolean;
  lastChecked: string | null;
  serverVersion: string | null;
  isChecking: boolean;
}

interface ServerStatusState extends ServerStatus {
  setOnline: (value: boolean) => void;
  setChecking: (value: boolean) => void;
  updateFromHealth: (health: HealthResponse) => void;
}

export const useServerStatusStore = create<ServerStatusState>((set) => ({
  isOnline: false,
  lastChecked: null,
  serverVersion: null,
  isChecking: false,
  setOnline: (value) =>
    set({
      isOnline: value,
      lastChecked: new Date().toISOString()
    }),
  setChecking: (value) => set({ isChecking: value }),
  updateFromHealth: (health) =>
    set({
      isOnline: health.status === 'ok',
      serverVersion: health.version,
      lastChecked: new Date().toISOString(),
      isChecking: false
    })
}));
