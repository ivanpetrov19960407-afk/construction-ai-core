import ChatWindow from '../components/ChatWindow';
import RoleSelector from '../components/RoleSelector';
import Card from '../components/ui/Card';

export default function ChatPage() {
  return (
    <Card>
      <div style={{ display: 'grid', gap: 12 }}>
        <RoleSelector />
        <ChatWindow />
      </div>
    </Card>
  );
}
