import Button from './ui/Button';
import { colors, spacing, zIndex } from '../styles/tokens';

interface ErrorModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  details?: Record<string, unknown>;
  trace?: string;
}

export default function ErrorModal({ isOpen, onClose, title, details, trace }: ErrorModalProps) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.55)',
        display: 'grid',
        placeItems: 'center',
        zIndex: zIndex.modal,
      }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        style={{
          width: 'min(720px, 92vw)',
          maxHeight: '80vh',
          overflow: 'auto',
          background: colors.bgCard,
          border: `1px solid ${colors.border}`,
          borderRadius: 12,
          padding: spacing.lg,
          boxShadow: '0 20px 45px rgba(2, 6, 23, 0.35)',
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <h3 style={{ marginTop: 0, marginBottom: spacing.sm }}>{title}</h3>
        <p style={{ color: colors.textSecondary }}>Технические детали ошибки:</p>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {JSON.stringify(details ?? {}, null, 2)}
        </pre>
        {trace && (
          <>
            <p style={{ marginTop: spacing.md, color: colors.textSecondary }}>Trace:</p>
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {trace}
            </pre>
          </>
        )}
        <div style={{ marginTop: spacing.md }}>
          <Button type="button" onClick={onClose}>
            Закрыть
          </Button>
        </div>
      </div>
    </div>
  );
}
