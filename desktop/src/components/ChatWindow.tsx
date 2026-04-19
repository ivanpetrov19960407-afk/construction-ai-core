import { FormEvent, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import Input from './ui/Input';
import Button from './ui/Button';
import { useChatStore } from '../store/chatStore';
import { sendChatMessage } from '../api/coreClient';
import type { ChatResponseMeta } from '../api/coreClient';
import { Store } from '@tauri-apps/plugin-store';
import { colors, radius, spacing } from '../styles/tokens';

export default function ChatWindow() {
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const messages = useChatStore((s) => s.messages);
  const role = useChatStore((s) => s.role);
  const defaultRole = useChatStore((s) => s.defaultRole);
  const sessionId = useChatStore((s) => s.sessionId);
  const addMessage = useChatStore((s) => s.addMessage);
  const isTyping = useChatStore((s) => s.isTyping);
  const setTyping = useChatStore((s) => s.setTyping);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages, isTyping]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    setError(null);
    addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      createdAt: new Date().toISOString()
    });
    setText('');
    setTyping(true);

    try {
      const settings = await Store.load('settings.json');
      const apiUrl = (await settings.get<string>('api_url')) || 'https://vanekpetrov1997.fvds.ru';
      const apiKey = (await settings.get<string>('api_key')) || '';

      const response = await sendChatMessage(apiUrl, apiKey, {
        message: trimmed,
        role: role || defaultRole,
        session_id: sessionId
      });
      const metadata: ChatResponseMeta = {
        agents: response.agents_used,
        confidence: typeof response.confidence === 'number' ? response.confidence : undefined
      };

      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.reply,
        createdAt: new Date().toISOString(),
        metadata
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка отправки сообщения');
    } finally {
      setTyping(false);
    }
  };

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm, flex: 1 }}>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          minHeight: 300,
          maxHeight: 'calc(100vh - 260px)',
          overflowY: 'auto',
          border: `1px solid ${colors.border}`,
          borderRadius: radius.lg,
          padding: spacing.md,
          display: 'flex',
          flexDirection: 'column',
          gap: spacing.sm
        }}
      >
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} metadata={message.metadata} className="message-enter" />
        ))}
        {isTyping && (
          <div style={{ display: 'flex', gap: 4, padding: '8px 12px', color: '#6b7280', fontSize: 13 }}>
            <span style={{ animation: 'fadeIn 0.6s ease infinite alternate' }}>●</span>
            <span style={{ animation: 'fadeIn 0.6s ease 0.2s infinite alternate' }}>●</span>
            <span style={{ animation: 'fadeIn 0.6s ease 0.4s infinite alternate' }}>●</span>
            <span style={{ marginLeft: 6 }}>Ассистент думает…</span>
          </div>
        )}
      </div>

      <div style={{ borderTop: `1px solid ${colors.border}`, paddingTop: spacing.md, marginTop: spacing.sm }}>
        <form onSubmit={onSubmit} style={{ display: 'flex', gap: spacing.sm, alignItems: 'center' }}>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Введите сообщение" style={{ flex: 1 }} />
          <Button type="submit">Отправить</Button>
        </form>
      </div>
      {error && <div style={{ color: colors.error }}>{error}</div>}
    </section>
  );
}
