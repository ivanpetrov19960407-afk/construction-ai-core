import type { ChatRole } from '../store/chatStore';

export interface ChatRequest {
  message: string;
  role: ChatRole;
  session_id: string;
}

export interface ChatResponse {
  reply: string;
}

export async function sendChatMessage(
  apiUrl: string,
  apiKey: string,
  payload: ChatRequest
): Promise<ChatResponse> {
  const response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}
