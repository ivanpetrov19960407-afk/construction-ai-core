import ChatWindow from '../components/ChatWindow';
import RoleSelector from '../components/RoleSelector';
import Sidebar from '../components/Sidebar';

export default function ChatPage() {
  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <Sidebar />
      <div style={{ flex: 1 }}>
        <RoleSelector />
        <ChatWindow />
      </div>
    </div>
  );
}
