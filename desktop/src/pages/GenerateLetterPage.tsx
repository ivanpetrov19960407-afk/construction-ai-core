import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import ErrorModal from '../components/ErrorModal';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import {
  downloadLetterDocx,
  generateLetterStream,
  getApiConfig,
  SSEError,
  type GenerationStage
} from '../api/coreClient';
import { DEFAULT_GENERATION_TIMEOUT_MS } from '../lib/apiClient';
import { validateLetter } from '../lib/validation';

const letterTypeMap: Record<string, 'запрос' | 'претензия' | 'уведомление' | 'ответ'> = {
  Запрос: 'запрос',
  Претензия: 'претензия',
  Уведомление: 'уведомление',
  Ответ: 'ответ'
};

const fields: DocumentField[] = [
  {
    name: 'letter_type',
    label: 'Тип письма',
    type: 'select',
    options: ['Запрос', 'Претензия', 'Уведомление', 'Ответ']
  },
  { name: 'addressee', label: 'Адресат', type: 'text' },
  { name: 'subject', label: 'Тема', type: 'text' },
  { name: 'body', label: 'Содержание', type: 'textarea' }
];

export default function GenerateLetterPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>('queued');
  const [toastMessage, setToastMessage] = useState('');
  const [sseError, setSseError] = useState<SSEError | null>(null);
  const [isErrorModalOpen, setIsErrorModalOpen] = useState(false);

  const handleSubmit = async (data: Record<string, string>) => {
    const bodyPoints = (data.body ?? '')
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean);

    const validation = validateLetter({
      addressee: data.addressee ?? '',
      subject: data.subject ?? '',
      body_points: bodyPoints
    });
    setValidationErrors(validation.fieldErrors);

    if (!validation.isValid) {
      setError('Исправьте ошибки формы перед отправкой.');
      setSuccess(false);
      return;
    }

    setIsLoading(true);
    setError('');
    setSuccess(false);
    setProgress(0);
    setStage('queued');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateLetterStream(
        apiUrl,
        apiKey,
        {
          letter_type: letterTypeMap[data.letter_type] ?? 'запрос',
          addressee: data.addressee?.trim() ?? '',
          subject: data.subject?.trim() ?? '',
          body_points: bodyPoints
        },
        (event) => {
          setProgress(event.progress ?? 0);
          setStage(event.stage);
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
      setSessionId(String(response.session_id ?? ''));
      setSuccess(true);
    } catch (submitError) {
      if (submitError instanceof SSEError) {
        setSseError(submitError);
        setToastMessage(submitError.message);
        setError(submitError.message);
      } else {
        setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации письма');
      }
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
      const blob = await downloadLetterDocx(apiUrl, apiKey, sessionId, {
        timeoutMs: DEFAULT_GENERATION_TIMEOUT_MS
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `letter-${sessionId}.docx`;
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
        <h2>Генерация письма</h2>
        <DocumentForm
          fields={fields}
          onSubmit={handleSubmit}
          onValuesChange={() => {
            if (Object.keys(validationErrors).length) {
              setValidationErrors({});
            }
            if (error === 'Исправьте ошибки формы перед отправкой.') {
              setError('');
            }
          }}
          isLoading={isLoading}
          error={error}
          fieldErrors={validationErrors}
        />
        {isLoading && <p style={{ color: colors.textSecondary }}>Текущий шаг: {stage} · {progress}%</p>}
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ Письмо сгенерировано</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {toastMessage && (
          <div style={{ border: `1px solid ${colors.error}`, borderRadius: 8, padding: spacing.sm, display: 'flex', gap: spacing.sm, alignItems: 'center' }}>
            <span style={{ color: colors.error, fontWeight: 600 }}>{toastMessage}</span>
            <Button type="button" variant="ghost" onClick={() => setIsErrorModalOpen(true)}>
              Подробнее
            </Button>
            {sseError?.code === 'llm_not_configured' && (
              <a href="/settings" style={{ color: colors.primary }}>
                Открыть Settings
              </a>
            )}
          </div>
        )}
        {sessionId && <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>}

        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />

        <Button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading} loading={downloadLoading}>
          {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
        </Button>
        <ErrorModal
          isOpen={Boolean(sseError) && isErrorModalOpen}
          onClose={() => setIsErrorModalOpen(false)}
          title={sseError?.message ?? 'Детали ошибки'}
          details={sseError?.details}
          trace={typeof sseError?.details?.trace === 'string' ? sseError.details.trace : undefined}
        />
      </section>
    </Card>
  );
}
