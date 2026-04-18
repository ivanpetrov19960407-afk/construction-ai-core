import { FormEvent, useEffect, useMemo, useState } from 'react';

export type DocumentFieldType = 'text' | 'number' | 'select' | 'textarea';

export interface DocumentField {
  name: string;
  label: string;
  type: DocumentFieldType;
  placeholder?: string;
  options?: string[];
}

interface DocumentFormProps {
  fields: DocumentField[];
  onSubmit: (data: Record<string, string>) => void;
  isLoading: boolean;
  error?: string;
  disabledOnLoading?: boolean;
}

const makeInitialValues = (fields: DocumentField[]): Record<string, string> =>
  fields.reduce<Record<string, string>>((acc, field) => {
    acc[field.name] = '';
    return acc;
  }, {});

export default function DocumentForm({
  fields,
  onSubmit,
  isLoading,
  error,
  disabledOnLoading = true
}: DocumentFormProps) {
  const initialValues = useMemo(() => makeInitialValues(fields), [fields]);
  const [values, setValues] = useState<Record<string, string>>(initialValues);

  useEffect(() => {
    setValues(initialValues);
  }, [initialValues]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(values);
  };

  const handleClear = () => {
    setValues(initialValues);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 12, maxWidth: 700 }}>
      {fields.map((field) => (
        <label key={field.name} style={{ display: 'grid', gap: 6 }}>
          <span>{field.label}</span>
          {field.type === 'textarea' ? (
            <textarea
              rows={6}
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              placeholder={field.placeholder}
              disabled={disabledOnLoading && isLoading}
              required
            />
          ) : field.type === 'select' ? (
            <select
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              disabled={disabledOnLoading && isLoading}
              required
            >
              <option value="" disabled>
                Выберите значение
              </option>
              {(field.options ?? []).map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={field.type}
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              placeholder={field.placeholder}
              disabled={disabledOnLoading && isLoading}
              required
            />
          )}
        </label>
      ))}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button type="submit" disabled={disabledOnLoading && isLoading}>
          {isLoading ? '⏳ Сгенерировать' : 'Сгенерировать'}
        </button>
        <button type="button" onClick={handleClear} disabled={disabledOnLoading && isLoading}>
          Очистить
        </button>
        {isLoading && <span role="status">⏳ Генерация...</span>}
      </div>
      {error && error.includes('Failed to fetch') && (
        <p style={{ color: '#8a6d3b' }}>Проверьте API URL и API Key в разделе Настройки</p>
      )}
    </form>
  );
}
