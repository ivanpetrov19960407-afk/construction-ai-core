import { type ButtonHTMLAttributes, useMemo, useState } from "react";
import { colors, radius, spacing, typography } from "../../styles/tokens";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const sizeStyles: Record<ButtonSize, { padding: string; fontSize: number }> = {
  sm: { padding: `${spacing.xs}px ${spacing.md}px`, fontSize: 12 },
  md: { padding: `${spacing.sm}px ${spacing.lg}px`, fontSize: 14 },
  lg: { padding: `${spacing.md}px ${spacing.xl}px`, fontSize: 15 },
};

const variantStyles: Record<
  ButtonVariant,
  {
    bg: string;
    color: string;
    border: string;
    hoverBg: string;
    activeBg: string;
  }
> = {
  primary: {
    bg: colors.primary,
    color: "#fff",
    border: colors.primary,
    hoverBg: colors.primaryHover,
    activeBg: colors.primaryActive,
  },
  secondary: {
    bg: "#fff",
    color: colors.textPrimary,
    border: colors.border,
    hoverBg: "#f3f4f6",
    activeBg: "#e5e7eb",
  },
  ghost: {
    bg: "transparent",
    color: colors.textPrimary,
    border: "transparent",
    hoverBg: "#f3f4f6",
    activeBg: "#e5e7eb",
  },
  danger: {
    bg: colors.error,
    color: "#fff",
    border: colors.error,
    hoverBg: "#991b1b",
    activeBg: "#7f1d1d",
  },
};

function Spinner() {
  return (
    <span
      aria-hidden
      style={{
        width: 14,
        height: 14,
        borderRadius: "50%",
        border: "2px solid rgba(255, 255, 255, 0.55)",
        borderTopColor: "currentColor",
        display: "inline-block",
        animation: "ui-spin 0.8s linear infinite",
      }}
    />
  );
}

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  onMouseEnter,
  onMouseLeave,
  onMouseDown,
  onMouseUp,
  style,
  ...rest
}: ButtonProps) {
  const [isHovered, setHovered] = useState(false);
  const [isActive, setActive] = useState(false);
  const isDisabled = disabled || loading;

  const palette = variantStyles[variant];
  const currentBg = useMemo(() => {
    if (isDisabled) {
      return variant === "ghost" ? "transparent" : "#9ca3af";
    }
    if (isActive) return palette.activeBg;
    if (isHovered) return palette.hoverBg;
    return palette.bg;
  }, [isDisabled, isActive, isHovered, palette, variant]);

  return (
    <>
      <style>
        {
          "@keyframes ui-spin { from { transform: rotate(0deg);} to { transform: rotate(360deg);} }"
        }
      </style>
      <button
        {...rest}
        disabled={isDisabled}
        onMouseEnter={(event) => {
          setHovered(true);
          onMouseEnter?.(event);
        }}
        onMouseLeave={(event) => {
          setHovered(false);
          setActive(false);
          onMouseLeave?.(event);
        }}
        onMouseDown={(event) => {
          setActive(true);
          onMouseDown?.(event);
        }}
        onMouseUp={(event) => {
          setActive(false);
          onMouseUp?.(event);
        }}
        style={{
          borderRadius: radius.md,
          border: `1px solid ${palette.border}`,
          background: currentBg,
          color: palette.color,
          cursor: isDisabled ? "not-allowed" : "pointer",
          fontFamily: typography.fontFamily,
          fontWeight: 600,
          lineHeight: 1.2,
          opacity: isDisabled ? 0.8 : 1,
          transition:
            "background-color 0.12s ease, transform 0.08s ease, opacity 0.12s ease",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: spacing.sm,
          ...(sizeStyles[size] ?? sizeStyles.md),
          ...style,
        }}
      >
        {loading && <Spinner />}
        {children}
      </button>
    </>
  );
}
