import type { ChatMessage } from '../store/chatStore';
import { colors, shadows, spacing } from '../styles/tokens';

export interface MessageMetadata {
  agents?: string[];
  confidence?: number;
}

interface Props {
  message: ChatMessage;
  metadata?: MessageMetadata;
  className?: string;
}

function getConfidenceBadge(confidence?: number) {
  if (typeof confidence !== 'number') {
    return null;
  }

  if (confidence >= 0.8) {
    return { label: '✓ Высокая', color: '#2e7d32' };
  }

  if (confidence >= 0.5) {
    return { label: '~ Средняя', color: '#f9a825' };
  }

  return { label: '? Низкая', color: '#9e9e9e' };
}

export default function MessageBubble({ message, metadata, className }: Props) {
  const isUser = message.role === 'user';
  const effectiveMetadata = metadata ?? message.metadata;
  const agents = effectiveMetadata?.agents ?? [];
  const confidenceBadge = getConfidenceBadge(effectiveMetadata?.confidence);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      // noop: в некоторых окружениях clipboard может быть недоступен
    }
  };

  return (
    <div className={className} style={{ alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: isUser ? '72%' : '80%' }}>
      <div
        style={{
          background: isUser ? colors.primary : colors.bgCard,
          border: isUser ? 'none' : `1px solid ${colors.border}`,
          color: isUser ? '#ffffff' : colors.textPrimary,
          borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
          padding: `${spacing.sm}px ${spacing.md}px`,
          boxShadow: shadows.sm
        }}
      >
        <strong style={{ display: 'block', marginBottom: 4 }}>{isUser ? 'Вы' : 'Assistant'}</strong>
        <span>{message.content}</span>
        {!isUser && (
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            {agents.map((agent) => (
              <span
                key={agent}
                style={{
                  background: '#f3f4f6',
                  color: '#4b5563',
                  borderRadius: 999,
                  padding: '2px 8px',
                  fontSize: 11,
                  fontWeight: 500
                }}
              >
                {agent}
              </span>
            ))}
            {confidenceBadge && (
              <span style={{ fontSize: 11, color: confidenceBadge.color }}>
                {confidenceBadge.label}
              </span>
            )}
            <button
              type="button"
              onClick={onCopy}
              style={{
                marginLeft: 'auto',
                fontSize: 12,
                color: '#666',
                background: 'transparent',
                border: '1px solid #d5d5d5',
                borderRadius: 8,
                cursor: 'pointer',
                padding: '2px 8px'
              }}
              aria-label="Копировать сообщение"
              title="Копировать"
            >
              📋 Копировать
            </button>
          </div>
        )}
      </div>
      <div
        style={{
          fontSize: 11,
          color: isUser ? 'rgba(255,255,255,0.65)' : colors.textMuted,
          textAlign: isUser ? 'right' : 'left',
          marginTop: 2
        }}
      >
        {new Date(message.createdAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
}
