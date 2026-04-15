import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { generateKS, getApiConfig } from '../api/coreClient';

const fields: DocumentField[] = [
  { name: 'object_name', label: 'Название объекта', type: 'text' },
  { name: 'contract_number', label: 'Номер договора', type: 'text' },
  { name: 'date_from', label: 'Период с', type: 'text', placeholder: 'YYYY-MM-DD' },
  { name: 'date_to', label: 'Период по', type: 'text', placeholder: 'YYYY-MM-DD' },
  {
    name: 'work_items',
    label: 'Перечень работ',
    type: 'textarea',
    placeholder: 'Этап 1: ...\nЭтап 2: ...'
  }
];

export default function GenerateKSPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (data: Record<string, string>) => {
    setIsLoading(true);
    setError('');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateKS(apiUrl, apiKey, {
        object_name: data.object_name,
        contract_number: data.contract_number,
        date_from: data.date_from,
        date_to: data.date_to,
        work_items: data.work_items
      });

      setResult(String(response.result ?? response.text ?? response.content ?? ''));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации КС');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <h2>Генерация КС</h2>
      <DocumentForm fields={fields} onSubmit={handleSubmit} isLoading={isLoading} />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <label style={{ display: 'grid', gap: 8 }}>
        <span>Результат</span>
        <textarea value={result} rows={12} readOnly />
      </label>
    </section>
  );
}
