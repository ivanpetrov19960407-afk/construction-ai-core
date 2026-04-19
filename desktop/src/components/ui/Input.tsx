import { type InputHTMLAttributes, type TextareaHTMLAttributes, useState } from 'react';
import { colors, radius, spacing, typography } from '../../styles/tokens';

type BaseProps = {
  label?: string;
  error?: string;
  hint?: string;
  type?: InputHTMLAttributes<HTMLInputElement>['type'] | 'textarea';
};

type InputProps = BaseProps &
  InputHTMLAttributes<HTMLInputElement> &
  TextareaHTMLAttributes<HTMLTextAreaElement>;

export default function Input({ label, error, hint, type = 'text', style, ...rest }: InputProps) {
  const [isFocused, setFocused] = useState(false);
  const message = error ?? hint;

  const commonStyle = {
    width: '100%',
    borderRadius: radius.md,
    border: `1px solid ${error ? colors.error : isFocused ? colors.borderFocus : colors.border}`,
    padding: `${spacing.sm}px ${spacing.md}px`,
    fontFamily: typography.fontFamily,
    fontSize: typography.body.fontSize,
    lineHeight: String(typography.body.lineHeight),
    color: colors.textPrimary,
    outline: 'none',
    background: '#fff',
    transition: 'border-color 0.12s ease, box-shadow 0.12s ease',
    boxShadow: isFocused ? `0 0 0 3px ${colors.primary}22` : 'none',
    ...style,
  } as const;

  return (
    <label style={{ display: 'grid', gap: spacing.xs }}>
      {label && (
        <span
          style={{
            color: colors.textPrimary,
            fontSize: typography.label.fontSize,
            fontWeight: typography.label.fontWeight,
          }}
        >
          {label}
        </span>
      )}
      {type === 'textarea' ? (
        <textarea
          {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
          onFocus={(event) => {
            setFocused(true);
            rest.onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            rest.onBlur?.(event);
          }}
          style={commonStyle}
        />
      ) : (
        <input
          {...(rest as InputHTMLAttributes<HTMLInputElement>)}
          type={type}
          onFocus={(event) => {
            setFocused(true);
            rest.onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            rest.onBlur?.(event);
          }}
          style={commonStyle}
        />
      )}
      {message && (
        <span
          style={{
            color: error ? colors.error : colors.textSecondary,
            fontSize: typography.small.fontSize,
          }}
        >
          {message}
        </span>
      )}
    </label>
  );
}
