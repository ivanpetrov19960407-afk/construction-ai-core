import { type FormEvent, useState } from 'react';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import ErrorModal from '../components/ErrorModal';
import Input from '../components/ui/Input';
import { generatePpr, getApiConfig, SSEError, type GenerationStage } from '../api/coreClient';
import { colors, spacing } from '../styles/tokens';

export default function GeneratePprPage() {
  const [workType, setWorkType] = useState('');
  const [objectName, setObjectName] = useState('');
  const [deadlineDays, setDeadlineDays] = useState('30');
  const [result, setResult] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>('queued');
  const [error, setError] = useState('');
  const [sseError, setSseError] = useState<SSEError | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setResult('');
    if (!workType.trim() || !objectName.trim() || Number(deadlineDays) <= 0) {
      setError('Заполните форму: тип работ, объект и срок (дней > 0).');
      return;
    }

    setIsLoading(true);
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generatePpr(
        apiUrl,
        apiKey,
        {
          work_type: workType.trim(),
          object_name: objectName.trim(),
          deadline_days: Number(deadlineDays),
        },
        (streamEvent) => {
          setProgress(streamEvent.progress ?? 0);
          setStage(streamEvent.stage);
        },
      );
      const output =
        response.result ?? response.text ?? response.content ?? JSON.stringify(response, null, 2);
      setResult(typeof output === 'string' ? output : JSON.stringify(output, null, 2));
    } catch (submitError) {
      if (submitError instanceof SSEError) {
        setSseError(submitError);
      }
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации ППР.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Генерация ППР</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>Главная / Генерация / ППР</p>
      <form onSubmit={onSubmit} style={{ display: 'grid', gap: spacing.md }}>
        <Input label="Тип работ" value={workType} onChange={(e) => setWorkType(e.target.value)} />
        <Input label="Объект" value={objectName} onChange={(e) => setObjectName(e.target.value)} />
        <Input
          label="Срок, дней"
          type="number"
          min={1}
          value={deadlineDays}
          onChange={(e) => setDeadlineDays(e.target.value)}
        />
        <Button type="submit" loading={isLoading}>
          {isLoading ? 'Генерация...' : 'Сгенерировать ППР'}
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
        <Input
          type="textarea"
          label="Результат"
          rows={14}
          readOnly
          value={result}
          style={{ marginTop: spacing.md }}
        />
      )}
      <ErrorModal
        isOpen={Boolean(sseError)}
        onClose={() => setSseError(null)}
        title={sseError?.message ?? 'Ошибка генерации'}
        details={sseError?.details}
      />
    </Card>
  );
}
