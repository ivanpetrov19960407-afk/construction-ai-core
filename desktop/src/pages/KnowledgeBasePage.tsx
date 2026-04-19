import { useEffect, useMemo, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import { checkHealth, getApiConfig, type HealthResponse } from '../api/coreClient';
import { colors, spacing } from '../styles/tokens';
import { useServerStatusStore } from '../store/serverStatusStore';

type PickedPdfFile = {
  path: string;
  name: string;
  size: number;
};

type UploadedDocument = {
  source: string;
  uploadedAt: string;
  size: number | null;
};

type SourcesResponse = {
  sources: Array<{ source: string; chunks: number }>;
};

const formatSize = (bytes: number | null) => {
  if (bytes === null || Number.isNaN(bytes)) {
    return '—';
  }

  if (bytes < 1024) {
    return `${bytes} Б`;
  }

  const kb = bytes / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(1)} КБ`;
  }

  return `${(kb / 1024).toFixed(2)} МБ`;
};

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [messageTone, setMessageTone] = useState<'success' | 'warning' | 'error'>('success');

  const fetchSources = async () => {
    const { apiUrl, apiKey } = await getApiConfig();
    const response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/rag/sources`, {
      method: 'GET',
      headers: {
        'X-API-Key': apiKey.trim()
      },
      signal: AbortSignal.timeout(10000)
    });

    if (!response.ok) {
      throw new Error(`Не удалось получить список документов (HTTP ${response.status}).`);
    }

    const payload = (await response.json()) as SourcesResponse;
    const nowIso = new Date().toISOString();
    setDocuments(
      payload.sources.map((source) => ({
        source: source.source,
        uploadedAt: nowIso,
        size: null
      }))
    );
  };

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      setMessage('');
      try {
        await fetchSources();
      } catch (error) {
        setMessageTone('error');
        setMessage(error instanceof Error ? error.message : 'Не удалось загрузить данные KB.');
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, []);

  const refreshServerStatus = async () => {
    const health: HealthResponse = await checkHealth((await getApiConfig()).apiUrl);
    useServerStatusStore.getState().updateFromHealth(health);
  };

  const onUploadPdf = async () => {
    setMessage('');
    setIsUploading(true);

    try {
      const selected = await invoke<PickedPdfFile | null>('pick_pdf_file');
      if (!selected) {
        setMessageTone('warning');
        setMessage('Загрузка отменена: файл не выбран.');
        return;
      }

      const fileBytes = await invoke<number[]>('read_pdf_file_bytes', { path: selected.path });
      const { apiUrl, apiKey } = await getApiConfig();
      const formData = new FormData();
      const fileBlob = new Blob([new Uint8Array(fileBytes)], { type: 'application/pdf' });
      formData.append('file', fileBlob, selected.name);
      formData.append('source_name', selected.name);

      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/rag/ingest`, {
        method: 'POST',
        headers: {
          'X-API-Key': apiKey.trim()
        },
        body: formData,
        signal: AbortSignal.timeout(60_000)
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Ошибка загрузки PDF (HTTP ${response.status}): ${body}`);
      }

      const uploadedAt = new Date().toISOString();
      setDocuments((prev) => {
        const withoutExisting = prev.filter((doc) => doc.source !== selected.name);
        return [{ source: selected.name, uploadedAt, size: selected.size }, ...withoutExisting];
      });

      await Promise.all([fetchSources(), refreshServerStatus()]);

      setMessageTone('success');
      setMessage(`Файл «${selected.name}» успешно загружен в KB.`);
    } catch (error) {
      setMessageTone('error');
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить PDF в базу знаний.');
    } finally {
      setIsUploading(false);
    }
  };

  const sortedDocuments = useMemo(
    () => [...documents].sort((a, b) => new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime()),
    [documents]
  );

  return (
    <Card>
      <div style={{ display: 'grid', gap: spacing.md }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: spacing.sm }}>
          <h2 style={{ margin: 0 }}>База знаний (KB)</h2>
          <Button onClick={onUploadPdf} disabled={isUploading} loading={isUploading}>
            {isUploading ? 'Загрузка...' : 'Загрузить PDF'}
          </Button>
        </div>

        {message && (
          <p
            style={{
              margin: 0,
              color: messageTone === 'success' ? colors.success : messageTone === 'warning' ? colors.warning : colors.error
            }}
          >
            {message}
          </p>
        )}

        {isLoading ? (
          <p style={{ margin: 0 }}>Загрузка списка документов…</p>
        ) : sortedDocuments.length === 0 ? (
          <p style={{ margin: 0, color: colors.warning }}>В базе знаний пока нет документов. Загрузите первый PDF.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}`, paddingBottom: spacing.xs }}>Имя файла</th>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}`, paddingBottom: spacing.xs }}>Дата загрузки</th>
                <th style={{ textAlign: 'left', borderBottom: `1px solid ${colors.border}`, paddingBottom: spacing.xs }}>Размер</th>
              </tr>
            </thead>
            <tbody>
              {sortedDocuments.map((doc) => (
                <tr key={doc.source}>
                  <td style={{ paddingTop: spacing.xs }}>{doc.source}</td>
                  <td style={{ paddingTop: spacing.xs }}>{new Date(doc.uploadedAt).toLocaleString('ru-RU')}</td>
                  <td style={{ paddingTop: spacing.xs }}>{formatSize(doc.size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}
