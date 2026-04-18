import { create } from 'zustand';
import type { ChatResponseMeta } from '../api/coreClient';

export type ChatRole = 'pto_engineer' | 'foreman' | 'tender_specialist' | 'admin';
export type MessageRole = 'user' | 'assistant';

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
  messages: ChatMessage[];
  sessions: ChatSession[];
  isTyping: boolean;
  setRole: (role: ChatRole) => void;
  addMessage: (message: ChatMessage) => void;
  setTyping: (isTyping: boolean) => void;
  resetSession: () => void;
}

const createSessionId = () => crypto.randomUUID();

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: createSessionId(),
  role: 'admin',
  messages: [],
  sessions: [],
  isTyping: false,
  setRole: (role) => set({ role }),
  addMessage: (message) => set({ messages: [...get().messages, message] }),
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
