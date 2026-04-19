import type { ChatMessage } from '../store/chatStore';

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
    <div
      className={className}
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        background: isUser ? '#d4f6dd' : '#f2f2f2',
        borderRadius: 12,
        padding: '10px 12px',
        maxWidth: '80%'
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
                fontSize: 11,
                color: '#777',
                border: '1px solid #d5d5d5',
                borderRadius: 999,
                padding: '1px 8px'
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
  );
}
