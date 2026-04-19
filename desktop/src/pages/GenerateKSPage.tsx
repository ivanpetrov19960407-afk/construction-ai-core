import { type FormEvent, useState } from 'react';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import { colors, radius, spacing, typography } from '../styles/tokens';
import {
  downloadKSDocx,
  generateKSStream,
  getApiConfig,
  type GenerationStage,
  type KSWorkItem
} from '../api/coreClient';
import { DEFAULT_GENERATION_TIMEOUT_MS } from '../lib/apiClient';

const unitOptions = ['м²', 'м³', 'пог.м.', 'шт.', 'т', 'кг', 'компл.', 'услуга'] as const;

interface WorkRow {
  id: string;
  name: string;
  unit: string;
  volume: string;
  normHours: string;
  pricePerUnit: string;
}

interface KSFormValues {
  objectName: string;
  contractNumber: string;
  dateFrom: string;
  dateTo: string;
}

function createEmptyWorkRow(): WorkRow {
  return {
    id: crypto.randomUUID(),
    name: '',
    unit: unitOptions[0],
    volume: '',
    normHours: '',
    pricePerUnit: ''
  };
}

function parseDateRU(val: string): string {
  const normalized = val.trim();
  const isoPattern = /^\d{4}-\d{2}-\d{2}$/;

  if (isoPattern.test(normalized)) {
    return normalized;
  }

  const ruPattern = /^(\d{2})\.(\d{2})\.(\d{4})$/;
  const ruMatch = normalized.match(ruPattern);

  if (!ruMatch) {
    throw new Error('Неверный формат даты. Используйте ДД.ММ.ГГГГ');
  }

  const [, dayStr, monthStr, yearStr] = ruMatch;
  const day = Number(dayStr);
  const month = Number(monthStr);
  const year = Number(yearStr);
  const parsedDate = new Date(Date.UTC(year, month - 1, day));

  if (
    parsedDate.getUTCFullYear() !== year ||
    parsedDate.getUTCMonth() + 1 !== month ||
    parsedDate.getUTCDate() !== day
  ) {
    throw new Error('Неверный формат даты. Используйте ДД.ММ.ГГГГ');
  }

  return `${yearStr}-${monthStr}-${dayStr}`;
}

interface KSSummary {
  ks2: string;
  ks3: string;
  total_cost: string;
  total_hours: string;
}

function formatDateRuFromIso(isoDate: string): string {
  if (!isoDate) return '—';
  const parsed = new Date(`${isoDate}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('ru-RU');
}

export default function GenerateKSPage() {
  const [formValues, setFormValues] = useState<KSFormValues>({
    objectName: '',
    contractNumber: '',
    dateFrom: '',
    dateTo: ''
  });
  const [workRows, setWorkRows] = useState<WorkRow[]>([createEmptyWorkRow()]);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [importInfo, setImportInfo] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [success, setSuccess] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [summary, setSummary] = useState<KSSummary | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>('queued');

  const handleRowChange = (rowId: string, key: keyof Omit<WorkRow, 'id'>, value: string) => {
    setWorkRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, [key]: value } : row)));
  };

  const addRow = () => {
    setWorkRows((prev) => [...prev, createEmptyWorkRow()]);
  };

  const removeRow = (rowId: string) => {
    setWorkRows((prev) => (prev.length > 1 ? prev.filter((row) => row.id !== rowId) : prev));
  };

  const buildWorkItems = (): KSWorkItem[] => {
    const zeroValueRows: string[] = [];
    const workItems = workRows
      .map((row) => ({ ...row, name: row.name.trim() }))
      .filter((row) => row.name.length > 0)
      .map((row) => {
        const volume = Number(row.volume || '0');
        const normHours = Number(row.normHours || '0');
        const pricePerUnit = Number(row.pricePerUnit || '0');

        if (
          Number.isNaN(volume) ||
          Number.isNaN(normHours) ||
          Number.isNaN(pricePerUnit) ||
          volume < 0 ||
          normHours < 0 ||
          pricePerUnit < 0
        ) {
          throw new Error(`Строка «${row.name}» содержит некорректные числовые значения.`);
        }

        if (volume === 0 || normHours === 0 || pricePerUnit === 0) {
          zeroValueRows.push(row.name);
        }

        return {
          name: row.name,
          unit: row.unit,
          volume,
          norm_hours: normHours,
          price_per_unit: pricePerUnit
        };
      });

    if (zeroValueRows.length) {
      setWarning(`Предупреждение: у работ с нулевыми значениями: ${zeroValueRows.join(', ')}.`);
    } else {
      setWarning('');
    }

    return workItems;
  };

  const handleImportFromClipboard = async () => {
    setError('');
    setWarning('');
    setImportInfo('');
    try {
      const clipboardText = await navigator.clipboard.readText();
      const importedRows = clipboardText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name = '', unit = unitOptions[0], volume = '', normHours = '', pricePerUnit = ''] = line
            .split('|')
            .map((part) => part.trim());

          if (!name) {
            return null;
          }

          return {
            id: crypto.randomUUID(),
            name,
            unit: unitOptions.includes(unit as (typeof unitOptions)[number]) ? unit : unitOptions[0],
            volume,
            normHours,
            pricePerUnit
          } as WorkRow;
        })
        .filter((row): row is WorkRow => row !== null);

      if (!importedRows.length) {
        throw new Error('В буфере обмена не найдено строк формата "Наименование|Ед.|Объём|Нормо-часы|Цена".');
      }

      setWorkRows(importedRows);
      setImportInfo(`Импортировано строк: ${importedRows.length}`);
    } catch (clipboardError) {
      setError(clipboardError instanceof Error ? clipboardError.message : 'Не удалось импортировать из буфера');
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setError('');
    setSuccess(false);
    setSummary(null);
    setImportInfo('');
    setProgress(0);
    setStage('queued');

    try {
      if (!formValues.objectName.trim()) {
        throw new Error('Заполните поле "Название объекта"');
      }
      if (!formValues.contractNumber.trim()) {
        throw new Error('Заполните поле "Номер договора"');
      }
      if (!formValues.dateFrom || !formValues.dateTo) {
        throw new Error('Заполните обе даты периода');
      }

      const workItems = buildWorkItems();

      if (!workItems.length) {
        throw new Error('Добавьте хотя бы одну строку работ');
      }

      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateKSStream(
        apiUrl,
        apiKey,
        {
          object_name: formValues.objectName.trim(),
          contract_number: formValues.contractNumber.trim(),
          period_from: parseDateRU(formValues.dateFrom),
          period_to: parseDateRU(formValues.dateTo),
          work_items: workItems
        },
        (event) => {
          setProgress(event.progress ?? 0);
          setStage(event.stage);
        }
      );

      setSessionId(String(response.session_id ?? ''));
      setSuccess(true);
      setSummary({
        ks2: String(response.ks2 ?? ''),
        ks3: String(response.ks3 ?? ''),
        total_cost: String(response.total_cost ?? ''),
        total_hours: String(response.total_hours ?? '')
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

  const handleDownload = async () => {
    if (!sessionId) {
      setError('Нет session_id для скачивания DOCX');
      return;
    }

    setDownloadLoading(true);
    setError('');

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const blob = await downloadKSDocx(apiUrl, apiKey, sessionId, {
        timeoutMs: DEFAULT_GENERATION_TIMEOUT_MS
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `ks-${sessionId}.docx`;
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
        <h2>Генерация КС</h2>
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: spacing.md, maxWidth: 900 }}>
          <Input
            label="Название объекта"
            value={formValues.objectName}
            onChange={(event) => setFormValues((prev) => ({ ...prev, objectName: event.target.value }))}
            disabled={isLoading}
            required
          />
          <Input
            label="Номер договора"
            value={formValues.contractNumber}
            onChange={(event) => setFormValues((prev) => ({ ...prev, contractNumber: event.target.value }))}
            disabled={isLoading}
            required
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
            <label style={{ display: 'grid', gap: spacing.xs }}>
              <span style={{ color: colors.textPrimary, fontSize: typography.label.fontSize, fontWeight: typography.label.fontWeight }}>
                Период с
              </span>
              <input
                type="date"
                value={formValues.dateFrom}
                onChange={(event) => {
                  const nextValue = event.currentTarget.valueAsDate
                    ? event.currentTarget.valueAsDate.toISOString().slice(0, 10)
                    : event.currentTarget.value;
                  setFormValues((prev) => ({ ...prev, dateFrom: nextValue }));
                }}
                min="1900-01-01"
                max="2100-12-31"
                required
                disabled={isLoading}
                style={{
                  width: '100%',
                  borderRadius: radius.md,
                  border: `1px solid ${colors.border}`,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  fontFamily: typography.fontFamily,
                  fontSize: typography.body.fontSize
                }}
              />
              <span style={{ color: colors.textSecondary, fontSize: typography.small.fontSize }}>
                {formatDateRuFromIso(formValues.dateFrom)}
              </span>
            </label>
            <label style={{ display: 'grid', gap: spacing.xs }}>
              <span style={{ color: colors.textPrimary, fontSize: typography.label.fontSize, fontWeight: typography.label.fontWeight }}>
                Период по
              </span>
              <input
                type="date"
                value={formValues.dateTo}
                onChange={(event) => {
                  const nextValue = event.currentTarget.valueAsDate
                    ? event.currentTarget.valueAsDate.toISOString().slice(0, 10)
                    : event.currentTarget.value;
                  setFormValues((prev) => ({ ...prev, dateTo: nextValue }));
                }}
                min="1900-01-01"
                max="2100-12-31"
                required
                disabled={isLoading}
                style={{
                  width: '100%',
                  borderRadius: radius.md,
                  border: `1px solid ${colors.border}`,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  fontFamily: typography.fontFamily,
                  fontSize: typography.body.fontSize
                }}
              />
              <span style={{ color: colors.textSecondary, fontSize: typography.small.fontSize }}>
                {formatDateRuFromIso(formValues.dateTo)}
              </span>
            </label>
          </div>
          <div style={{ display: 'grid', gap: spacing.sm }}>
            <span style={{ color: colors.textPrimary, fontSize: typography.label.fontSize, fontWeight: typography.label.fontWeight }}>
              Перечень работ
            </span>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 860 }}>
                <thead>
                  <tr>
                    {['Наименование работ', 'Ед. изм.', 'Объём', 'Нормо-часы', 'Цена за ед.', ''].map((title) => (
                      <th
                        key={title || 'actions'}
                        style={{
                          border: `1px solid ${colors.border}`,
                          padding: spacing.sm,
                          textAlign: 'left',
                          backgroundColor: '#f9fafb',
                          fontSize: typography.small.fontSize
                        }}
                      >
                        {title}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {workRows.map((row) => (
                    <tr key={row.id}>
                      <td style={{ border: `1px solid ${colors.border}`, padding: spacing.xs }}>
                        <Input
                          value={row.name}
                          onChange={(event) => handleRowChange(row.id, 'name', event.target.value)}
                          placeholder="Наименование работы"
                          disabled={isLoading}
                        />
                      </td>
                      <td style={{ border: `1px solid ${colors.border}`, padding: spacing.xs }}>
                        <select
                          value={row.unit}
                          onChange={(event) => handleRowChange(row.id, 'unit', event.target.value)}
                          disabled={isLoading}
                          style={{
                            width: '100%',
                            borderRadius: radius.md,
                            border: `1px solid ${colors.border}`,
                            padding: `${spacing.sm}px ${spacing.md}px`,
                            fontFamily: typography.fontFamily,
                            fontSize: typography.body.fontSize
                          }}
                        >
                          {unitOptions.map((unit) => (
                            <option key={unit} value={unit}>
                              {unit}
                            </option>
                          ))}
                        </select>
                      </td>
                      {(['volume', 'normHours', 'pricePerUnit'] as const).map((field) => (
                        <td key={`${row.id}-${field}`} style={{ border: `1px solid ${colors.border}`, padding: spacing.xs }}>
                          <Input
                            type="number"
                            min="0"
                            step="0.01"
                            value={row[field]}
                            onChange={(event) => handleRowChange(row.id, field, event.target.value)}
                            placeholder="0.00"
                            disabled={isLoading}
                          />
                        </td>
                      ))}
                      <td style={{ border: `1px solid ${colors.border}`, padding: spacing.xs, textAlign: 'center' }}>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => removeRow(row.id)}
                          disabled={workRows.length === 1 || isLoading}
                          title={workRows.length === 1 ? 'Должна оставаться минимум одна строка' : 'Удалить строку'}
                        >
                          ✕
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: 'flex', gap: spacing.sm, flexWrap: 'wrap' }}>
              <Button type="button" variant="secondary" onClick={addRow} disabled={isLoading}>
                + Добавить строку
              </Button>
              <Button type="button" variant="secondary" onClick={handleImportFromClipboard} disabled={isLoading}>
                Импорт из буфера
              </Button>
            </div>
            {importInfo && <p style={{ color: colors.textSecondary }}>{importInfo}</p>}
          </div>
          <div style={{ display: 'flex', gap: spacing.sm, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button type="submit" loading={isLoading} disabled={isLoading}>
              {isLoading ? 'Сгенерировать...' : 'Сгенерировать'}
            </Button>
            {isLoading && <span role="status">⏳ Генерация...</span>}
          </div>
          {isLoading && (
            <div style={{ display: 'grid', gap: spacing.xs }}>
              <div style={{ color: colors.textSecondary }}>Текущий шаг: {stage}</div>
              <div style={{ width: '100%', height: 8, background: '#e5e7eb', borderRadius: 999 }}>
                <div
                  style={{
                    width: `${progress}%`,
                    height: 8,
                    background: colors.primary,
                    borderRadius: 999,
                    transition: 'width 200ms ease'
                  }}
                />
              </div>
            </div>
          )}
        </form>
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ КС сгенерирована</p>}
        {warning && <p style={{ color: colors.warning }}>{warning}</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {sessionId && <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>}
        {summary && (
          <p style={{ color: colors.textPrimary, fontWeight: 600 }}>
            Итого работ: {workRows.filter((row) => row.name.trim()).length} | Общая стоимость: {summary.total_cost || '0'} руб. | Всего
            нормо-часов: {summary.total_hours || '0'} ч.
          </p>
        )}
        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />
        <Button type="button" onClick={handleDownload} disabled={!sessionId || downloadLoading} loading={downloadLoading}>
          {downloadLoading ? 'Скачивание...' : 'Скачать DOCX'}
        </Button>
      </section>
    </Card>
  );
}
