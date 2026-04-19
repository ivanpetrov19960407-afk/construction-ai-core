import type { KSWorkItem } from '../api/coreClient';

export interface TKValidationInput {
  work_type: string;
  object_name: string;
  volume: number;
  unit: string;
}

export interface KSValidationInput {
  object_name: string;
  contract_number: string;
  period_from: string;
  period_to: string;
  work_items: KSWorkItem[];
}

export interface LetterValidationInput {
  addressee: string;
  subject: string;
  body_points: string[];
}

export interface ValidationResult {
  fieldErrors: Record<string, string>;
  isValid: boolean;
}

const DATE_ISO_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DATE_RU_PATTERN = /^(\d{2})\.(\d{2})\.(\d{4})$/;

function toIsoDate(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return null;

  if (DATE_ISO_PATTERN.test(normalized)) {
    const parsed = new Date(`${normalized}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return normalized;
  }

  const ruMatch = normalized.match(DATE_RU_PATTERN);
  if (!ruMatch) {
    return null;
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
    return null;
  }

  return `${yearStr}-${monthStr}-${dayStr}`;
}

export function validateTK(input: TKValidationInput): ValidationResult {
  const fieldErrors: Record<string, string> = {};

  if (input.work_type.trim().length < 5) {
    fieldErrors.work_type = 'Тип работ: минимум 5 символов.';
  }
  if (input.object_name.trim().length < 3) {
    fieldErrors.object_name = 'Название объекта: минимум 3 символа.';
  }
  if (!Number.isFinite(input.volume) || input.volume <= 0) {
    fieldErrors.volume = 'Объём должен быть числом больше 0.';
  }
  if (!input.unit.trim()) {
    fieldErrors.unit = 'Выберите единицу измерения.';
  }

  return { fieldErrors, isValid: Object.keys(fieldErrors).length === 0 };
}

export function validateKS(input: KSValidationInput): ValidationResult {
  const fieldErrors: Record<string, string> = {};

  if (input.object_name.trim().length < 3) {
    fieldErrors.object_name = 'Название объекта: минимум 3 символа.';
  }
  if (input.contract_number.trim().length < 2) {
    fieldErrors.contract_number = 'Номер договора: минимум 2 символа.';
  }

  const periodFrom = toIsoDate(input.period_from);
  const periodTo = toIsoDate(input.period_to);

  if (!input.period_from.trim()) {
    fieldErrors.period_from = 'Укажите дату начала периода.';
  } else if (!periodFrom) {
    fieldErrors.period_from = 'Используйте формат ДД.ММ.ГГГГ или YYYY-MM-DD.';
  }

  if (!input.period_to.trim()) {
    fieldErrors.period_to = 'Укажите дату окончания периода.';
  } else if (!periodTo) {
    fieldErrors.period_to = 'Используйте формат ДД.ММ.ГГГГ или YYYY-MM-DD.';
  }

  if (periodFrom && periodTo && periodFrom > periodTo) {
    fieldErrors.period_to = 'Дата окончания не может быть раньше даты начала.';
  }

  if (!input.work_items.length) {
    fieldErrors.work_items = 'Добавьте хотя бы одну работу.';
  }

  input.work_items.forEach((item, index) => {
    const row = index + 1;
    if (item.name.trim().length < 2) {
      fieldErrors[`work_items.${index}.name`] = `Строка ${row}: минимум 2 символа в наименовании.`;
    }
    if (!Number.isFinite(item.volume) || item.volume <= 0) {
      fieldErrors[`work_items.${index}.volume`] = `Строка ${row}: объём должен быть > 0.`;
    }
    if (!Number.isFinite(item.norm_hours) || item.norm_hours <= 0) {
      fieldErrors[`work_items.${index}.norm_hours`] = `Строка ${row}: нормо-часы должны быть > 0.`;
    }
    if (!Number.isFinite(item.price_per_unit) || item.price_per_unit <= 0) {
      fieldErrors[`work_items.${index}.price_per_unit`] = `Строка ${row}: цена должна быть > 0.`;
    }
  });

  return { fieldErrors, isValid: Object.keys(fieldErrors).length === 0 };
}

export function validateLetter(input: LetterValidationInput): ValidationResult {
  const fieldErrors: Record<string, string> = {};

  if (input.addressee.trim().length < 3) {
    fieldErrors.addressee = 'Адресат: минимум 3 символа.';
  }
  if (input.subject.trim().length < 5) {
    fieldErrors.subject = 'Тема: минимум 5 символов.';
  }

  const cleanedPoints = input.body_points.map((item) => item.trim()).filter(Boolean);
  if (cleanedPoints.length === 0) {
    fieldErrors.body = 'Добавьте хотя бы один тезис в содержании письма.';
  } else if (cleanedPoints.some((item) => item.length < 3)) {
    fieldErrors.body = 'Каждый тезис должен содержать минимум 3 символа.';
  }

  return { fieldErrors, isValid: Object.keys(fieldErrors).length === 0 };
}
