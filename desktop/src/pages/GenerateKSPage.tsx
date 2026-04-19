import { type FormEvent, useState } from 'react';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import ErrorModal from '../components/ErrorModal';
import Input from '../components/ui/Input';
import { colors, radius, spacing, typography } from '../styles/tokens';
import {
  downloadKSDocx,
  generateKSStream,
  getApiConfig,
  type GenerationStage,
  type KS2Data,
  type KS3Data,
  type KSGenerationResponse,
  type KSHeader,
  type KSWorkItem,
} from '../api/coreClient';
import { SSEError } from '../api/coreClient';
import { DEFAULT_GENERATION_TIMEOUT_MS } from '../lib/apiClient';
import { validateKS } from '../lib/validation';

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
    pricePerUnit: '',
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
  header: KSHeader;
  ks2: KS2Data;
  ks3: KS3Data;
  total_cost: number;
  total_hours: number;
}

function formatDateRuFromIso(isoDate: string): string {
  if (!isoDate) return '—';
  let normalizedIso = isoDate;
  try {
    normalizedIso = parseDateRU(isoDate);
  } catch {
    return '—';
  }
  const parsed = new Date(`${normalizedIso}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('ru-RU');
}

export default function GenerateKSPage() {
  const [formValues, setFormValues] = useState<KSFormValues>({
    objectName: '',
    contractNumber: '',
    dateFrom: '',
    dateTo: '',
  });
  const [workRows, setWorkRows] = useState<WorkRow[]>([createEmptyWorkRow()]);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [importInfo, setImportInfo] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [success, setSuccess] = useState(false);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [summary, setSummary] = useState<KSSummary | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>('queued');
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [toastMessage, setToastMessage] = useState('');
  const [sseError, setSseError] = useState<SSEError | null>(null);
  const [isErrorModalOpen, setIsErrorModalOpen] = useState(false);

  const handleRowChange = (rowId: string, key: keyof Omit<WorkRow, 'id'>, value: string) => {
    setWorkRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, [key]: value } : row)));
    if (Object.keys(validationErrors).length > 0) {
      setValidationErrors({});
    }
    if (error === 'Исправьте ошибки формы перед отправкой.') {
      setError('');
    }
  };

  const addRow = () => {
    setWorkRows((prev) => [...prev, createEmptyWorkRow()]);
  };

  const removeRow = (rowId: string) => {
    setWorkRows((prev) => (prev.length > 1 ? prev.filter((row) => row.id !== rowId) : prev));
  };

  const buildWorkItems = (rows: WorkRow[] = workRows): KSWorkItem[] => {
    return rows.map((row) => ({
      name: row.name.trim(),
      unit: row.unit,
      volume: Number(row.volume),
      norm_hours: Number(row.normHours),
      price_per_unit: Number(row.pricePerUnit),
    }));
  };

  const handleImportFromClipboard = async () => {
    setError('');
    setImportInfo('');
    try {
      const clipboardText = await navigator.clipboard.readText();
      const importedRows = clipboardText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name = '', unit = unitOptions[0], volume = '', normHours = '', pricePerUnit = ''] =
            line.split('|').map((part) => part.trim());

          if (!name) {
            return null;
          }

          return {
            id: crypto.randomUUID(),
            name,
            unit: unitOptions.includes(unit as (typeof unitOptions)[number])
              ? unit
              : unitOptions[0],
            volume,
            normHours,
            pricePerUnit,
          } as WorkRow;
        })
        .filter((row): row is WorkRow => row !== null);

      if (!importedRows.length) {
        throw new Error(
          'В буфере обмена не найдено строк формата "Наименование|Ед.|Объём|Нормо-часы|Цена".',
        );
      }

      setWorkRows(importedRows);
      setImportInfo(`Импортировано строк: ${importedRows.length}`);
    } catch (clipboardError) {
      setError(
        clipboardError instanceof Error
          ? clipboardError.message
          : 'Не удалось импортировать из буфера',
      );
    }
  };

  const normalizeKSResponse = (
    response: KSGenerationResponse,
    payloadHeader: KSHeader,
  ): KSSummary => {
    const normalizedKs2Raw = (
      response.ks2 && typeof response.ks2 === 'object' ? response.ks2 : {}
    ) as Partial<KS2Data>;
    const normalizedKs3Raw = (
      response.ks3 && typeof response.ks3 === 'object' ? response.ks3 : {}
    ) as Partial<KS3Data>;

    const header: KSHeader = {
      object_name:
        normalizedKs2Raw.object_name || normalizedKs3Raw.object_name || payloadHeader.object_name,
      contract_number:
        normalizedKs2Raw.contract_number ||
        normalizedKs3Raw.contract_number ||
        payloadHeader.contract_number,
      period_from:
        normalizedKs2Raw.period_from || normalizedKs3Raw.period_from || payloadHeader.period_from,
      period_to:
        normalizedKs2Raw.period_to || normalizedKs3Raw.period_to || payloadHeader.period_to,
    };

    const workItems = Array.isArray(normalizedKs2Raw.work_items) ? normalizedKs2Raw.work_items : [];
    const ks2: KS2Data = {
      ...header,
      work_items: workItems,
      total_cost: Number(normalizedKs2Raw.total_cost ?? response.total_cost ?? 0),
      total_hours: Number(normalizedKs2Raw.total_hours ?? response.total_hours ?? 0),
    };
    const ks3: KS3Data = {
      ...header,
      period_days: Number(normalizedKs3Raw.period_days ?? 0),
      total_cost: Number(normalizedKs3Raw.total_cost ?? response.total_cost ?? 0),
      total_hours: Number(normalizedKs3Raw.total_hours ?? response.total_hours ?? 0),
      workers_needed: Number(normalizedKs3Raw.workers_needed ?? 0),
    };

    return {
      header,
      ks2,
      ks3,
      total_cost: Number(response.total_cost ?? ks2.total_cost ?? 0),
      total_hours: Number(response.total_hours ?? ks2.total_hours ?? 0),
    };
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
    setValidationErrors({});

    try {
      const workItems = buildWorkItems(workRows);

      const validation = validateKS({
        object_name: formValues.objectName,
        contract_number: formValues.contractNumber,
        period_from: formValues.dateFrom,
        period_to: formValues.dateTo,
        work_items: workItems,
      });

      if (!validation.isValid) {
        setValidationErrors(validation.fieldErrors);
        throw new Error('Исправьте ошибки формы перед отправкой.');
      }

      const payloadHeader: KSHeader = {
        object_name: formValues.objectName.trim(),
        contract_number: formValues.contractNumber.trim(),
        period_from: parseDateRU(formValues.dateFrom),
        period_to: parseDateRU(formValues.dateTo),
      };
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateKSStream(
        apiUrl,
        apiKey,
        {
          ...payloadHeader,
          work_items: workItems,
        },
        (event) => {
          setProgress(event.progress ?? 0);
          setStage(event.stage);
        },
      );

      setSessionId(String(response.session_id ?? ''));
      setSuccess(true);
      const normalized = normalizeKSResponse(response, payloadHeader);
      setSummary(normalized);

      const normalizedResult = response.document ?? {
        session_id: response.session_id,
        docx_bytes_key: response.docx_bytes_key,
        sha256: response.sha256,
        header: normalized.header,
        ks2: normalized.ks2,
        ks3: normalized.ks3,
        total_cost: normalized.total_cost,
        total_hours: normalized.total_hours,
      };
      setResult(
        typeof normalizedResult === 'string'
          ? normalizedResult
          : JSON.stringify(normalizedResult, null, 2),
      );
    } catch (submitError) {
      if (submitError instanceof SSEError) {
        setSseError(submitError);
        setToastMessage(submitError.message);
        setError(submitError.message);
      } else {
        setError(submitError instanceof Error ? submitError.message : 'Ошибка генерации КС');
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
      const blob = await downloadKSDocx(apiUrl, apiKey, sessionId, {
        timeoutMs: DEFAULT_GENERATION_TIMEOUT_MS,
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
            onChange={(event) => {
              setFormValues((prev) => ({ ...prev, objectName: event.target.value }));
              if (Object.keys(validationErrors).length > 0) setValidationErrors({});
              if (error === 'Исправьте ошибки формы перед отправкой.') setError('');
            }}
            disabled={isLoading}
            required
          />
          {validationErrors.object_name && (
            <p style={{ color: colors.error }}>{validationErrors.object_name}</p>
          )}
          <Input
            label="Номер договора"
            value={formValues.contractNumber}
            onChange={(event) => {
              setFormValues((prev) => ({ ...prev, contractNumber: event.target.value }));
              if (Object.keys(validationErrors).length > 0) setValidationErrors({});
              if (error === 'Исправьте ошибки формы перед отправкой.') setError('');
            }}
            disabled={isLoading}
            required
          />
          {validationErrors.contract_number && (
            <p style={{ color: colors.error }}>{validationErrors.contract_number}</p>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
            <label style={{ display: 'grid', gap: spacing.xs }}>
              <span
                style={{
                  color: colors.textPrimary,
                  fontSize: typography.label.fontSize,
                  fontWeight: typography.label.fontWeight,
                }}
              >
                Период с
              </span>
              <input
                type="text"
                value={formValues.dateFrom}
                onChange={(event) => {
                  const nextValue = event.currentTarget.value.trim();
                  setFormValues((prev) => ({ ...prev, dateFrom: nextValue }));
                  if (Object.keys(validationErrors).length > 0) setValidationErrors({});
                  if (error === 'Исправьте ошибки формы перед отправкой.') setError('');
                }}
                placeholder="ДД.ММ.ГГГГ или YYYY-MM-DD"
                required
                disabled={isLoading}
                style={{
                  width: '100%',
                  borderRadius: radius.md,
                  border: `1px solid ${colors.border}`,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  fontFamily: typography.fontFamily,
                  fontSize: typography.body.fontSize,
                }}
              />
              <span style={{ color: colors.textSecondary, fontSize: typography.small.fontSize }}>
                {formatDateRuFromIso(formValues.dateFrom)}
              </span>
              {validationErrors.period_from && (
                <span style={{ color: colors.error }}>{validationErrors.period_from}</span>
              )}
            </label>
            <label style={{ display: 'grid', gap: spacing.xs }}>
              <span
                style={{
                  color: colors.textPrimary,
                  fontSize: typography.label.fontSize,
                  fontWeight: typography.label.fontWeight,
                }}
              >
                Период по
              </span>
              <input
                type="text"
                value={formValues.dateTo}
                onChange={(event) => {
                  const nextValue = event.currentTarget.value.trim();
                  setFormValues((prev) => ({ ...prev, dateTo: nextValue }));
                  if (Object.keys(validationErrors).length > 0) setValidationErrors({});
                  if (error === 'Исправьте ошибки формы перед отправкой.') setError('');
                }}
                placeholder="ДД.ММ.ГГГГ или YYYY-MM-DD"
                required
                disabled={isLoading}
                style={{
                  width: '100%',
                  borderRadius: radius.md,
                  border: `1px solid ${colors.border}`,
                  padding: `${spacing.sm}px ${spacing.md}px`,
                  fontFamily: typography.fontFamily,
                  fontSize: typography.body.fontSize,
                }}
              />
              <span style={{ color: colors.textSecondary, fontSize: typography.small.fontSize }}>
                {formatDateRuFromIso(formValues.dateTo)}
              </span>
              {validationErrors.period_to && (
                <span style={{ color: colors.error }}>{validationErrors.period_to}</span>
              )}
            </label>
          </div>
          <div style={{ display: 'grid', gap: spacing.sm }}>
            <span
              style={{
                color: colors.textPrimary,
                fontSize: typography.label.fontSize,
                fontWeight: typography.label.fontWeight,
              }}
            >
              Перечень работ
            </span>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 860 }}>
                <thead>
                  <tr>
                    {[
                      'Наименование работ',
                      'Ед. изм.',
                      'Объём',
                      'Нормо-часы',
                      'Цена за ед.',
                      '',
                    ].map((title) => (
                      <th
                        key={title || 'actions'}
                        style={{
                          border: `1px solid ${colors.border}`,
                          padding: spacing.sm,
                          textAlign: 'left',
                          backgroundColor: '#f9fafb',
                          fontSize: typography.small.fontSize,
                        }}
                      >
                        {title}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {workRows.map((row, rowIndex) => (
                    <tr key={row.id}>
                      <td style={{ border: `1px solid ${colors.border}`, padding: spacing.xs }}>
                        <Input
                          error={validationErrors[`work_items.${rowIndex}.name`]}
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
                            fontSize: typography.body.fontSize,
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
                        <td
                          key={`${row.id}-${field}`}
                          style={{ border: `1px solid ${colors.border}`, padding: spacing.xs }}
                        >
                          <Input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={row[field]}
                            onChange={(event) => handleRowChange(row.id, field, event.target.value)}
                            placeholder="0.00"
                            error={
                              validationErrors[
                                `work_items.${rowIndex}.${field === 'normHours' ? 'norm_hours' : field === 'pricePerUnit' ? 'price_per_unit' : field}`
                              ]
                            }
                            disabled={isLoading}
                          />
                        </td>
                      ))}
                      <td
                        style={{
                          border: `1px solid ${colors.border}`,
                          padding: spacing.xs,
                          textAlign: 'center',
                        }}
                      >
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => removeRow(row.id)}
                          disabled={workRows.length === 1 || isLoading}
                          title={
                            workRows.length === 1
                              ? 'Должна оставаться минимум одна строка'
                              : 'Удалить строку'
                          }
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
              <Button
                type="button"
                variant="secondary"
                onClick={handleImportFromClipboard}
                disabled={isLoading}
              >
                Импорт из буфера
              </Button>
            </div>
            {importInfo && <p style={{ color: colors.textSecondary }}>{importInfo}</p>}
            {validationErrors.work_items && (
              <p style={{ color: colors.error }}>{validationErrors.work_items}</p>
            )}
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
                    transition: 'width 200ms ease',
                  }}
                />
              </div>
            </div>
          )}
        </form>
        {success && <p style={{ color: colors.success, fontWeight: 600 }}>✓ КС сгенерирована</p>}
        {error && <p style={{ color: colors.error }}>{error}</p>}
        {toastMessage && (
          <div
            style={{
              border: `1px solid ${colors.error}`,
              borderRadius: 8,
              padding: spacing.sm,
              display: 'flex',
              gap: spacing.sm,
              alignItems: 'center',
            }}
          >
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
        {sessionId && (
          <p style={{ color: colors.textSecondary, fontSize: 12 }}>session_id: {sessionId}</p>
        )}
        {summary && (
          <p style={{ color: colors.textPrimary, fontWeight: 600 }}>
            Итого работ: {summary.ks2.work_items.length} | Общая стоимость:{' '}
            {summary.total_cost || 0} руб. | Всего нормо-часов: {summary.total_hours || 0} ч.
          </p>
        )}
        <Input type="textarea" label="Результат" value={result} rows={12} readOnly />
        <Button
          type="button"
          onClick={handleDownload}
          disabled={!sessionId || downloadLoading}
          loading={downloadLoading}
        >
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
