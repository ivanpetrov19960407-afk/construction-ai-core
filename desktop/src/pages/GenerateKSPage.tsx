import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import { downloadKSDocx, generateKS, getApiConfig, type KSWorkItem } from '../api/coreClient';

const fields: DocumentField[] = [
  { name: 'object_name', label: 'Название объекта', type: 'text' },
  { name: 'contract_number', label: 'Номер договора', type: 'text' },
  { name: 'date_from', label: 'Период с', type: 'text', placeholder: 'ДД.ММ.ГГГГ' },
  { name: 'date_to', label: 'Период по', type: 'text', placeholder: 'ДД.ММ.ГГГГ' },
  {
    name: 'work_items',
    label: 'Перечень работ',
    type: 'textarea',
    placeholder: 'Наименование|Ед.|Объём|Нормо-часы|Цена\nБетонирование|м³|10|2|5000'
  }
];

function parseDateRU(val: string): string {
  const normalized = val.trim();
  const isoPattern = /^\d{4}-\d{2}-\d{2}$/;

  if (isoPattern.test(normalized)) {
    return normalized;
  }

  const ruPattern = /^(\d{2})\.(\d{2})\.(\d{4})$/;
  const ruMatch = normalized.match(ruPattern);

  if (!ruMatch) {
    throw new Error('Неверный формат даты. Используйте ДД.ММ.ГГГГ');
  }

  const [, dayStr, monthStr, yearStr] = ruMatch;
  const day = Number(dayStr);
  const month = Number(monthStr);
  const year = Number(yearStr);
  const parsedDate = new Date(Date.UTC(year, month - 1, day));

  if (
    parsedDate.getUTCFullYear() !== year ||
    parsedDate.getUTCMonth() + 1 !== month ||
    parsedDate.getUTCDate() !== day
  ) {
    throw new Error('Неверный формат даты. Используйте ДД.ММ.ГГГГ');
  }

  return `${yearStr}-${monthStr}-${dayStr}`;
}

interface KSSummary {
  ks2: string;
  ks3: string;
  total_cost: string;
  total_hours: string;
}

export default function GenerateKSPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [success, setSuccess] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [summary, setSummary] = useState<KSSummary | null>(null);

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');
    setSuccess(false);
    setSummary(null);

    try {
      const workItems: KSWorkItem[] = data.work_items
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name, unit, volume, normHours, pricePerUnit] = line
            .split('|')
            .map((part) => part.trim());

          if (!name || !unit || !volume || !normHours || !pricePerUnit) {
            throw new Error(
              'Каждая строка work_items должна быть в формате: Наименование|Ед.|Объём|Нормо-часы|Цена'
            );
          }

          return {
            name,
            unit,
            volume: Number(volume),
            norm_hours: Number(normHours),
            price_per_unit: Number(pricePerUnit)
          };
        });

      if (!workItems.length) {
        throw new Error('Добавьте хотя бы одну строку работ');
      }

      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateKS(apiUrl, apiKey, {
        object_name: data.object_name,
        contract_number: data.contract_number,
        period_from: parseDateRU(data.date_from),
        period_to: parseDateRU(data.date_to),
        work_items: workItems
      });

      setSessionId(String(response.session_id ?? ''));
      setSuccess(true);
      setSummary({
        ks2: String(response.ks2 ?? ''),
        ks3: String(response.ks3 ?? ''),
        total_cost: String(response.total_cost ?? ''),
        total_hours: String(response.total_hours ?? '')
      });

      const normalizedResult =
        response.document ??
        (response.ks2 || response.ks3
          ? { ks2: response.ks2, ks3: response.ks3, total_cost: response.total_cost, total_hours: response.total_hours }
          : response.result ?? response.text ?? response.content ?? '');
      setResult(
        typeof normalizedResult === 'string'
          ? normalizedResult
          : JSON.stringify(normalizedResult, null, 2)
      );
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации КС');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!sessionId) {
      setError('Нет session_id для скачивания DOCX');
      return;
    }

    setDownloadLoading(true);
    setError('');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const blob = await downloadKSDocx(apiUrl, apiKey, sessionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `ks-${sessionId}.docx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Ошибка скачивания DOCX');
    } finally {
      setDownloadLoading(false);
    }
  };

  return (
    <Card>
      <section style={{ display: 'grid', gap: spacing.md }}>
        <h2>Генерация КС</h2>
        <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} error={error} />
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ КС сгенерирована</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {sessionId && <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>}
        {summary && (
          <table style={{ borderCollapse: 'collapse', width: '100%', maxWidth: 700 }}>
            <thead>
              <tr>
                <th style={{ border: `1px solid ${colors.border}`, padding: 8 }}>ks2 (стоимость)</th>
                <th style={{ border: `1px solid ${colors.border}`, padding: 8 }}>ks3 (выполнение)</th>
                <th style={{ border: `1px solid ${colors.border}`, padding: 8 }}>total_cost</th>
                <th style={{ border: `1px solid ${colors.border}`, padding: 8 }}>total_hours</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ border: `1px solid ${colors.border}`, padding: 8 }}>{summary.ks2 || '—'}</td>
                <td style={{ border: `1px solid ${colors.border}`, padding: 8 }}>{summary.ks3 || '—'}</td>
                <td style={{ border: `1px solid ${colors.border}`, padding: 8 }}>{summary.total_cost || '—'}</td>
                <td style={{ border: `1px solid ${colors.border}`, padding: 8 }}>{summary.total_hours || '—'}</td>
              </tr>
            </tbody>
          </table>
        )}
        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />
        <Button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading} loading={downloadLoading}>
          {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
        </Button>
      </section>
    </Card>
  );
}
