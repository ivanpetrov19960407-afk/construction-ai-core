import { create } from 'zustand';
import { Store } from '@tauri-apps/plugin-store';
import type { ChatResponseMeta } from '../api/coreClient';

export type ChatRole = 'pto_engineer' | 'foreman' | 'tender_specialist' | 'admin';
export type MessageRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  metadata?: ChatResponseMeta;
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
}

interface ChatState {
  sessionId: string;
  role: ChatRole;
  defaultRole: ChatRole;
  messages: ChatMessage[];
  sessions: ChatSession[];
  isTyping: boolean;
  setRole: (role: ChatRole) => void;
  setDefaultRole: (role: ChatRole) => void;
  addMessage: (message: ChatMessage) => void;
  upsertMessage: (message: ChatMessage) => void;
  setTyping: (isTyping: boolean) => void;
  resetSession: () => void;
}

const createSessionId = () => crypto.randomUUID();

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: createSessionId(),
  role: 'pto_engineer',
  defaultRole: 'pto_engineer',
  messages: [],
  sessions: [],
  isTyping: false,
  setRole: (role) => set({ role }),
  setDefaultRole: (role) => set({ defaultRole: role, role }),
  addMessage: (message) =>
    set((state) => {
      if (state.messages.some((item) => item.id === message.id)) {
        return state;
      }
      return { messages: [...state.messages, message] };
    }),
  upsertMessage: (message) =>
    set((state) => {
      const index = state.messages.findIndex((item) => item.id === message.id);
      if (index === -1) {
        return { messages: [...state.messages, message] };
      }
      const messages = [...state.messages];
      messages[index] = message;
      return { messages };
    }),
  setTyping: (isTyping) => set({ isTyping }),
  resetSession: () => {
    const prev = get();
    const nextId = createSessionId();
    const title = prev.messages[0]?.content?.slice(0, 30) || 'Новая сессия';

    set({
      sessions: [
        { id: prev.sessionId, title, createdAt: new Date().toISOString() },
        ...prev.sessions
      ],
      sessionId: nextId,
      messages: [],
      isTyping: false
    });
  }
}));

void (async () => {
  const store = await Store.load('settings.json');
  const defaultRole = await store.get<ChatRole>('default_role');

  if (defaultRole) {
    useChatStore.setState({ defaultRole, role: defaultRole });
  }
})();
