import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import { colors, spacing } from '../styles/tokens';
import { downloadLetterDocx, generateLetter, getApiConfig } from '../api/coreClient';

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

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');
    setSuccess(false);

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const bodyPoints = data.body
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean);

      const response = await generateLetter(apiUrl, apiKey, {
        letter_type: letterTypeMap[data.letter_type] ?? 'запрос',
        addressee: data.addressee,
        subject: data.subject,
        body_points: bodyPoints
      });

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
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации письма');
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
      const blob = await downloadLetterDocx(apiUrl, apiKey, sessionId);
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
        <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} error={error} />
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ Письмо сгенерировано</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {sessionId && <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>}

        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />

        <Button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading} loading={downloadLoading}>
          {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
        </Button>
      </section>
    </Card>
  );
}
