import { type PropsWithChildren } from 'react';
import { colors, radius, spacing } from '../../styles/tokens';

interface CardProps extends PropsWithChildren {
  padding?: keyof typeof spacing;
  shadow?: boolean;
  style?: React.CSSProperties;
}

export default function Card({ children, padding = 'lg', shadow = true, style }: CardProps) {
  return (
    <section
      style={{
        background: colors.bgCard,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.lg,
        padding: spacing[padding],
        boxShadow: shadow ? '0 6px 16px rgba(15, 23, 42, 0.08)' : 'none',
        ...style,
      }}
    >
      {children}
    </section>
  );
}
