export const colors = {
  primary: '#2563eb',
  primaryHover: '#1d4ed8',
  primaryActive: '#1e40af',
  success: '#15803d',
  warning: '#b45309',
  error: '#b91c1c',
  textPrimary: '#111827',
  textSecondary: '#6b7280',
  textMuted: '#9ca3af',
  bgPage: '#f9fafb',
  bgCard: '#ffffff',
  bgSidebar: '#f3f4f6',
  bgActiveNav: '#dbeafe',
  border: '#e5e7eb',
  borderFocus: '#2563eb'
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16
} as const;

export const typography = {
  fontFamily: 'Inter, system-ui, Arial, sans-serif',
  h1: { fontSize: 24, fontWeight: 700, lineHeight: 1.3 },
  h2: { fontSize: 20, fontWeight: 600, lineHeight: 1.4 },
  body: { fontSize: 14, fontWeight: 400, lineHeight: 1.6 },
  small: { fontSize: 12, fontWeight: 400, lineHeight: 1.5 },
  label: { fontSize: 13, fontWeight: 500, lineHeight: 1.4 }
} as const;
