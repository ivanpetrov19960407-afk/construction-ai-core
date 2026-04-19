import type { ReactNode } from 'react';
import ChatPage from './pages/ChatPage';
import GenerateKSPage from './pages/GenerateKSPage';
import GenerateLetterPage from './pages/GenerateLetterPage';
import GenerateTKPage from './pages/GenerateTKPage';
import HandoverPage from './pages/HandoverPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import SettingsPage from './pages/SettingsPage';
import GeneratePprPage from './pages/GeneratePprPage';
import GenerateEstimatePage from './pages/GenerateEstimatePage';
import AnalyzeTenderPage from './pages/AnalyzeTenderPage';
import GenerateExecAlbumPage from './pages/GenerateExecAlbumPage';
import AnalyticsDashboardPage from './pages/AnalyticsDashboardPage';
import CompliancePage from './pages/CompliancePage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import BillingPage from './pages/BillingPage';
import { useAuth } from './context/AuthContext';

function RequireAuth({ children, requireAdmin = false }: { children: ReactNode; requireAdmin?: boolean }) {
  const { me, loading } = useAuth();

  if (loading) {
    return <p>Проверка авторизации...</p>;
  }

  if (!me) {
    return <LoginPage />;
  }

  if (requireAdmin && !me.is_admin) {
    return <p>Доступно только для роли admin.</p>;
  }

  return <>{children}</>;
}

export function resolveRoute(path: string, onNavigateHome: () => void): ReactNode {
  switch (path) {
    case '/':
      return <RequireAuth><ChatPage /></RequireAuth>;
    case '/settings':
      return <RequireAuth><SettingsPage /></RequireAuth>;
    case '/knowledge-base':
      return <RequireAuth><KnowledgeBasePage /></RequireAuth>;
    case '/generate/tk':
      return <RequireAuth><GenerateTKPage /></RequireAuth>;
    case '/generate/letter':
      return <RequireAuth><GenerateLetterPage /></RequireAuth>;
    case '/generate/ks':
      return <RequireAuth><GenerateKSPage /></RequireAuth>;
    case '/generate/ppr':
      return <RequireAuth><GeneratePprPage /></RequireAuth>;
    case '/generate/estimate':
      return <RequireAuth><GenerateEstimatePage /></RequireAuth>;
    case '/generate/exec-album':
      return <RequireAuth><GenerateExecAlbumPage /></RequireAuth>;
    case '/analyze/tender':
      return <RequireAuth><AnalyzeTenderPage /></RequireAuth>;
    case '/analytics':
      return <RequireAuth requireAdmin><AnalyticsDashboardPage /></RequireAuth>;
    case '/compliance':
      return <RequireAuth requireAdmin><CompliancePage /></RequireAuth>;
    case '/billing':
      return <RequireAuth requireAdmin><BillingPage /></RequireAuth>;
    case '/register':
      return <RegisterPage />;
    case '/login':
      return <LoginPage />;
    case '/handover':
      return <RequireAuth><HandoverPage /></RequireAuth>;
    case '/diagnostics':
      return <RequireAuth><DiagnosticsPage /></RequireAuth>;
    default:
      return (
        <section>
          <h2>Страница не найдена</h2>
          <button onClick={onNavigateHome}>На главную</button>
        </section>
      );
  }
}
