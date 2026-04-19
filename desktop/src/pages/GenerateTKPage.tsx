import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import { downloadTKDocx, generateTK, getApiConfig } from '../api/coreClient';
import { DEFAULT_GENERATION_TIMEOUT_MS } from '../lib/apiClient';

const fields: DocumentField[] = [
  { name: 'work_type', label: 'Тип работ', type: 'text' },
  { name: 'object_name', label: 'Название объекта', type: 'text' },
  { name: 'volume', label: 'Объём', type: 'number' },
  {
    name: 'unit',
    label: 'Единица измерения',
    type: 'select',
    options: ['м³', 'м²', 'пог.м.', 'шт.', 'т', 'кг']
  }
];

export default function GenerateTKPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [documentJson, setDocumentJson] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');
    setSuccess(false);

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateTK(
        apiUrl,
        apiKey,
        {
          work_type: data.work_type,
          object_name: data.object_name,
          volume: Number(data.volume),
          unit: data.unit
        },
        { timeoutMs: DEFAULT_GENERATION_TIMEOUT_MS }
      );

      const normalizedResult =
        response.document ?? response.result ?? response.text ?? response.content ?? '';
      setResult(
        typeof normalizedResult === 'string'
          ? normalizedResult
          : JSON.stringify(normalizedResult, null, 2)
      );
      setDocumentJson(response.document ? JSON.stringify(response.document, null, 2) : '');
      setSessionId(String(response.session_id ?? ''));
      setSuccess(true);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации ТК');
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
      const blob = await downloadTKDocx(apiUrl, apiKey, sessionId, {
        timeoutMs: DEFAULT_GENERATION_TIMEOUT_MS
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tk-${sessionId}.docx`;
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
        <h2>Генерация ТК</h2>
        <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} error={error} />
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ ТК сгенерирована</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {sessionId && <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>}

        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />

        {documentJson && <Input type="textarea" label="document (JSON)" value={documentJson} rows={10} readOnly />}

        <Button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading} loading={downloadLoading}>
          {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
        </Button>
      </section>
    </Card>
  );
}
