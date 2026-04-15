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
}

const makeInitialValues = (fields: DocumentField[]): Record<string, string> =>
  fields.reduce<Record<string, string>>((acc, field) => {
    acc[field.name] = '';
    return acc;
  }, {});

export default function DocumentForm({ fields, onSubmit, isLoading }: DocumentFormProps) {
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
              required
            />
          ) : field.type === 'select' ? (
            <select
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
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
              required
            />
          )}
        </label>
      ))}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button type="submit" disabled={isLoading}>
          Сгенерировать
        </button>
        <button type="button" onClick={handleClear} disabled={isLoading}>
          Очистить
        </button>
        {isLoading && <span role="status">⏳ Генерация...</span>}
      </div>
    </form>
  );
}
