import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { downloadTKDocx, generateTK, getApiConfig } from '../api/coreClient';

const fields: DocumentField[] = [
  { name: 'work_type', label: 'Тип работ', type: 'text' },
  { name: 'object_name', label: 'Название объекта', type: 'text' },
  { name: 'volume', label: 'Объём', type: 'number' },
  { name: 'unit', label: 'Единица измерения', type: 'select', options: ['м³', 'м²', 'шт'] }
];

export default function GenerateTKPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [error, setError] = useState('');
  const [downloadLoading, setDownloadLoading] = useState(false);

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateTK(apiUrl, apiKey, {
        work_type: data.work_type,
        object_name: data.object_name,
        volume: data.volume,
        unit: data.unit
      });

      setResult(String(response.result ?? response.text ?? response.content ?? ''));
      setSessionId(String(response.session_id ?? ''));
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
      <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <label style={{ display: 'grid', gap: 8 }}>
        <span>Результат</span>
        <textarea value={result} rows={12} readOnly />
      </label>
      <button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading}>
        {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
      </button>
    </section>
  );
}
