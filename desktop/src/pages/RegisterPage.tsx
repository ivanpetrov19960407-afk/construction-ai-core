import { type FormEvent, useState } from 'react';
import { Store } from '@tauri-apps/plugin-store';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Input from '../components/ui/Input';
import { getApiConfig, register } from '../api/coreClient';
import { colors, spacing } from '../styles/tokens';

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('pto_engineer');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Заполните логин и пароль.');
      return;
    }
    setLoading(true);

    try {
      const { apiUrl } = await getApiConfig();
      const auth = await register(apiUrl, { username: username.trim(), password, role });
      const token = auth.access_token?.trim();
      if (!token) {
        throw new Error('Сервер не вернул access_token.');
      }
      const store = await Store.load('settings.json');
      await store.set('api_key', token);
      await store.save();
      window.dispatchEvent(new Event('auth:credentials-changed'));
      window.history.pushState({}, '', '/');
      window.dispatchEvent(new PopStateEvent('popstate'));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка регистрации.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Регистрация</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>Главная / Авторизация / Регистрация</p>
      <form onSubmit={onSubmit} style={{ display: 'grid', gap: spacing.md }}>
        <Input label="Логин" value={username} onChange={(e) => setUsername(e.target.value)} />
        <Input label="Пароль" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <label>
          Роль
          <select value={role} onChange={(e) => setRole(e.target.value)} style={{ width: '100%', marginTop: spacing.xs, padding: spacing.sm }}>
            <option value="pto_engineer">pto_engineer</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <Button type="submit" loading={loading}>{loading ? 'Регистрация...' : 'Зарегистрироваться'}</Button>
      </form>
      {error && <p style={{ color: colors.error }}>{error}</p>}
    </Card>
  );
}
