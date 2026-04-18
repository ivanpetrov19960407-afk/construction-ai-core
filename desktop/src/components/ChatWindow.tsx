import { FormEvent, useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import { useChatStore } from '../store/chatStore';
import { sendChatMessage } from '../api/coreClient';
import type { ChatResponseMeta } from '../api/coreClient';
import { Store } from '@tauri-apps/plugin-store';

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
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
      <div
        ref={containerRef}
        style={{
          height: 460,
          overflowY: 'auto',
          border: '1px solid #ddd',
          borderRadius: 12,
          padding: 10,
          display: 'flex',
          flexDirection: 'column',
          gap: 8
        }}
      >
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} metadata={message.metadata} />
        ))}
        {isTyping && <div style={{ color: '#777' }}>Assistant печатает…</div>}
      </div>

      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Введите сообщение"
          style={{ flex: 1, padding: '8px 10px' }}
        />
        <button type="submit">Отправить</button>
      </form>
      {error && <div style={{ color: '#b00020' }}>{error}</div>}
    </section>
  );
}
