import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { generateLetter, getApiConfig } from '../api/coreClient';

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
  const [error, setError] = useState('');

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateLetter(apiUrl, apiKey, {
        letter_type: data.letter_type,
        addressee: data.addressee,
        subject: data.subject,
        body: data.body
      });

      setResult(String(response.result ?? response.text ?? response.content ?? ''));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации письма');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <h2>Генерация письма</h2>
      <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <label style={{ display: 'grid', gap: 8 }}>
        <span>Результат</span>
        <textarea value={result} rows={12} readOnly />
      </label>
    </section>
  );
}
