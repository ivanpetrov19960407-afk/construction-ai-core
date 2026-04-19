import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getApiConfig, getMe, type MeResponse } from '../api/coreClient';

type AuthContextValue = {
  me: MeResponse | null;
  isAdmin: boolean;
  loading: boolean;
  reload: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    setLoading(true);
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      if (!apiKey.trim()) {
        setMe(null);
        return;
      }
      const profile = await getMe(apiUrl, apiKey);
      setMe(profile);
    } catch (_error) {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  useEffect(() => {
    const handleReload = () => {
      void loadMe();
    };

    window.addEventListener('auth:credentials-changed', handleReload);
    window.addEventListener('focus', handleReload);

    return () => {
      window.removeEventListener('auth:credentials-changed', handleReload);
      window.removeEventListener('focus', handleReload);
    };
  }, [loadMe]);

  const value = useMemo<AuthContextValue>(
    () => ({
      me,
      isAdmin: Boolean(me?.is_admin),
      loading,
      reload: loadMe,
    }),
    [loadMe, loading, me],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
