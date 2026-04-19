import { type FormEvent, useState } from 'react';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import ErrorModal from '../components/ErrorModal';
import Input from '../components/ui/Input';
import { generateEstimate, getApiConfig, SSEError, type GenerationStage } from '../api/coreClient';
import { colors, spacing } from '../styles/tokens';

export default function GenerateEstimatePage() {
  const [base, setBase] = useState<'ГЭСН' | 'ФЕР'>('ГЭСН');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState('');
  const [downloadPayload, setDownloadPayload] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>('queued');
  const [error, setError] = useState('');
  const [sseError, setSseError] = useState<SSEError | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (!file) {
      setError('Загрузите ведомость объёмов (xlsx/csv/pdf).');
      return;
    }

    setIsLoading(true);
    try {
      const boqText = await file.text();
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateEstimate(
        apiUrl,
        apiKey,
        {
          base,
          boq_file_name: file.name,
          boq_text: boqText.slice(0, 500_000),
        },
        (streamEvent) => {
          setProgress(streamEvent.progress ?? 0);
          setStage(streamEvent.stage);
        },
      );
      const output =
        response.result ?? response.text ?? response.content ?? JSON.stringify(response, null, 2);
      const outputText = typeof output === 'string' ? output : JSON.stringify(output, null, 2);
      setResult(outputText);
      setDownloadPayload(outputText);
    } catch (submitError) {
      if (submitError instanceof SSEError) {
        setSseError(submitError);
      }
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации сметы.');
    } finally {
      setIsLoading(false);
    }
  };

  const onDownload = () => {
    if (!downloadPayload) return;
    const blob = new Blob([downloadPayload], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `estimate-${Date.now()}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Генерация сметы</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>Главная / Генерация / Смета</p>
      <form onSubmit={onSubmit} style={{ display: 'grid', gap: spacing.md }}>
        <label>
          База норм
          <select
            value={base}
            onChange={(e) => setBase(e.target.value as 'ГЭСН' | 'ФЕР')}
            style={{ width: '100%', marginTop: spacing.xs, padding: spacing.sm }}
          >
            <option value="ГЭСН">ГЭСН</option>
            <option value="ФЕР">ФЕР</option>
          </select>
        </label>
        <input type="file" onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)} />
        <Button type="submit" loading={isLoading}>
          {isLoading ? 'Генерация...' : 'Сгенерировать смету'}
        </Button>
      </form>
      {isLoading && (
        <div style={{ marginTop: spacing.md }}>
          <div style={{ color: colors.textSecondary, marginBottom: spacing.xs }}>Шаг: {stage}</div>
          <div style={{ width: '100%', height: 8, background: '#e5e7eb', borderRadius: 999 }}>
            <div
              style={{
                width: `${progress}%`,
                height: 8,
                background: colors.primary,
                borderRadius: 999,
              }}
            />
          </div>
        </div>
      )}
      {error && <p style={{ color: colors.error }}>{error}</p>}
      {result && (
        <div style={{ display: 'grid', gap: spacing.sm, marginTop: spacing.md }}>
          <Input type="textarea" label="Результат" rows={14} readOnly value={result} />
          <Button type="button" onClick={onDownload}>
            Скачать XLSX
          </Button>
        </div>
      )}
      <ErrorModal
        isOpen={Boolean(sseError)}
        onClose={() => setSseError(null)}
        title={sseError?.message ?? 'Ошибка'}
        details={sseError?.details}
      />
    </Card>
  );
}
