import { create } from 'zustand';

export interface BrandingConfig {
  org_id: string;
  company_name: string;
  logo_url: string;
  primary_color: string;
  accent_color: string;
  favicon_url: string;
  support_email: string;
  custom_domain: string;
}

interface BrandingState {
  branding: BrandingConfig | null;
  setBranding: (branding: BrandingConfig) => void;
}

export const useBrandingStore = create<BrandingState>((set) => ({
  branding: null,
  setBranding: (branding) => set({ branding })
}));
