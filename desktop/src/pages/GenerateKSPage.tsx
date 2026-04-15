import { useState } from 'react';
import DocumentForm, { type DocumentField } from '../components/DocumentForm';
import { generateKS, getApiConfig, type KSWorkItem } from '../api/coreClient';

const fields: DocumentField[] = [
  { name: 'object_name', label: 'Название объекта', type: 'text' },
  { name: 'contract_number', label: 'Номер договора', type: 'text' },
  { name: 'date_from', label: 'Период с', type: 'text', placeholder: 'YYYY-MM-DD' },
  { name: 'date_to', label: 'Период по', type: 'text', placeholder: 'YYYY-MM-DD' },
  {
    name: 'work_items',
    label: 'Перечень работ',
    type: 'textarea',
    placeholder: 'Наименование|Ед.|Объём|Нормо-часы|Цена\nБетонирование|м³|10|2|5000'
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
      const workItems: KSWorkItem[] = data.work_items
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name, unit, volume, normHours, pricePerUnit] = line
            .split('|')
            .map((part) => part.trim());

          if (!name || !unit || !volume || !normHours || !pricePerUnit) {
            throw new Error(
              'Каждая строка work_items должна быть в формате: Наименование|Ед.|Объём|Нормо-часы|Цена'
            );
          }

          return {
            name,
            unit,
            volume: Number(volume),
            norm_hours: Number(normHours),
            price_per_unit: Number(pricePerUnit)
          };
        });

      if (!workItems.length) {
        throw new Error('Добавьте хотя бы одну строку работ');
      }

      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateKS(apiUrl, apiKey, {
        object_name: data.object_name,
        contract_number: data.contract_number,
        period_from: data.date_from,
        period_to: data.date_to,
        work_items: workItems
      });

      const normalizedResult =
        response.document ??
        (response.ks2 || response.ks3
          ? { ks2: response.ks2, ks3: response.ks3, total_cost: response.total_cost, total_hours: response.total_hours }
          : response.result ?? response.text ?? response.content ?? '');
      setResult(
        typeof normalizedResult === 'string'
          ? normalizedResult
          : JSON.stringify(normalizedResult, null, 2)
      );
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
