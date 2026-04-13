import type { ChatMessage } from '../store/chatStore';

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div
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
    </div>
  );
}
