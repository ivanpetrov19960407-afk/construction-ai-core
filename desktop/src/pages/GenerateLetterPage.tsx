import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { generateLetter, getApiConfig } from '../api/coreClient';


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
  const [error, setError] = useState('');

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');

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
