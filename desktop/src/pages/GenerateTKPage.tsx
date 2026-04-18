import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { downloadTKDocx, generateTK, getApiConfig } from '../api/coreClient';

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
      const response = await generateTK(apiUrl, apiKey, {
        work_type: data.work_type,
        object_name: data.object_name,
        volume: Number(data.volume),
        unit: data.unit
      });

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
      const blob = await downloadTKDocx(apiUrl, apiKey, sessionId);
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
    <section style={{ display: 'grid', gap: 12 }}>
      <h2>Генерация ТК</h2>
      <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} error={error} />
      {success && <p style={{ color: 'green', fontWeight: 600 }}>✓ ТК сгенерирована</p>}
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      {sessionId && <p style={{ color: '#777', fontSize: 12 }}>session_id: {sessionId}</p>}
      <label style={{ display: 'grid', gap: 8 }}>
        <span>Результат</span>
        <textarea value={result} rows={12} readOnly />
      </label>
      {documentJson && (
        <label style={{ display: 'grid', gap: 8 }}>
          <span>document (JSON)</span>
          <textarea value={documentJson} rows={10} readOnly />
        </label>
      )}
      <button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading}>
        {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
      </button>
    </section>
  );
}
