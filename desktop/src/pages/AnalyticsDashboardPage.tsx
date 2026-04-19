import { useEffect, useState } from 'react';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import { getAnalyticsSummary, getApiConfig } from '../api/coreClient';
import type { AnalyticsSummaryResponse } from '../types/api';
import { colors, spacing } from '../styles/tokens';

export default function AnalyticsDashboardPage() {
  const [summary, setSummary] = useState<AnalyticsSummaryResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await getAnalyticsSummary(apiUrl, apiKey);
      setSummary(response);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Не удалось загрузить аналитику.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Аналитика</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>Главная / Админ / Аналитика</p>
      <Button type="button" onClick={() => void load()} loading={loading}>{loading ? 'Обновление...' : 'Обновить'}</Button>
      {error && <p style={{ color: colors.error }}>{error}</p>}
      {summary && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(140px, 1fr))', gap: spacing.sm, marginTop: spacing.md }}>
            <Card padding="md" shadow={false}><strong>Генерации</strong><div>{summary.total_generations ?? 0}</div></Card>
            <Card padding="md" shadow={false}><strong>Токены</strong><div>{summary.total_tokens ?? 0}</div></Card>
            <Card padding="md" shadow={false}><strong>Средний отклик</strong><div>{summary.avg_response_ms ?? 0} ms</div></Card>
          </div>
          <table style={{ width: '100%', marginTop: spacing.md, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th align="left">Дата</th><th align="right">Генерации</th><th align="right">Токены</th><th align="right">Отклик, ms</th>
              </tr>
            </thead>
            <tbody>
              {(summary.by_day ?? []).map((row) => (
                <tr key={row.date}>
                  <td>{row.date}</td><td align="right">{row.generations}</td><td align="right">{row.tokens}</td><td align="right">{row.avg_response_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}
