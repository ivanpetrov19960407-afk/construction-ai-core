import { FormEvent, useEffect, useMemo, useState } from 'react';
import Button from './ui/Button';
import Input from './ui/Input';
import { colors, radius, spacing, typography } from '../styles/tokens';

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
  onValuesChange?: (data: Record<string, string>) => void;
  isLoading: boolean;
  error?: string;
  disabledOnLoading?: boolean;
  fieldErrors?: Record<string, string>;
}

const makeInitialValues = (fields: DocumentField[]): Record<string, string> =>
  fields.reduce<Record<string, string>>((acc, field) => {
    acc[field.name] = '';
    return acc;
  }, {});

export default function DocumentForm({
  fields,
  onSubmit,
  onValuesChange,
  isLoading,
  error,
  disabledOnLoading = true,
  fieldErrors = {},
}: DocumentFormProps) {
  const initialValues = useMemo(() => makeInitialValues(fields), [fields]);
  const [values, setValues] = useState<Record<string, string>>(initialValues);

  useEffect(() => {
    setValues(initialValues);
  }, [initialValues]);

  useEffect(() => {
    onValuesChange?.(values);
  }, [onValuesChange, values]);
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(values);
  };

  const handleClear = () => {
    setValues(initialValues);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'grid', gap: spacing.md, maxWidth: 700 }}>
      {fields.map((field) => (
        <div key={field.name}>
          {field.type === 'textarea' ? (
            <Input
              error={fieldErrors[field.name]}
              type="textarea"
              rows={6}
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              placeholder={field.placeholder}
              disabled={disabledOnLoading && isLoading}
              required
              label={field.label}
            />
          ) : field.type === 'select' ? (
            <label style={{ display: 'grid', gap: spacing.xs }}>
              <span
                style={{
                  color: colors.textPrimary,
                  fontSize: typography.label.fontSize,
                  fontWeight: typography.label.fontWeight,
                }}
              >
                {field.label}
              </span>
              <select
                value={values[field.name] ?? ''}
                onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
                disabled={disabledOnLoading && isLoading}
                required
                style={{
                  width: '100%',
                  borderRadius: radius.md,
                  border: `1px solid ${colors.border}`,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  fontFamily: typography.fontFamily,
                  fontSize: typography.body.fontSize,
                }}
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
              {fieldErrors[field.name] && (
                <span style={{ color: colors.error, fontSize: typography.small.fontSize }}>
                  {fieldErrors[field.name]}
                </span>
              )}
            </label>
          ) : (
            <Input
              error={fieldErrors[field.name]}
              type={field.type}
              value={values[field.name] ?? ''}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              placeholder={field.placeholder}
              disabled={disabledOnLoading && isLoading}
              required
              label={field.label}
            />
          )}
        </div>
      ))}

      <div style={{ display: 'flex', gap: spacing.sm, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button type="submit" loading={isLoading} disabled={disabledOnLoading && isLoading}>
          {isLoading ? 'Сгенерировать...' : 'Сгенерировать'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={handleClear}
          disabled={disabledOnLoading && isLoading}
        >
          Очистить
        </Button>
        {isLoading && <span role="status">⏳ Генерация...</span>}
      </div>
      {error && error.includes('Failed to fetch') && (
        <p style={{ color: colors.warning }}>Проверьте API URL и API Key в разделе Настройки</p>
      )}
    </form>
  );
}
