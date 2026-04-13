import { FormEvent, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Store } from '@tauri-apps/plugin-store';

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState('http://localhost:8000');
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const load = async () => {
      const store = await Store.load('settings.json');
      const url = (await store.get<string>('api_url')) || (await invoke<string>('get_api_url'));
      const key = (await store.get<string>('api_key')) || '';
      setApiUrl(url);
      setApiKey(key);
    };

    void load();
  }, []);

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    const store = await Store.load('settings.json');
    await store.set('api_url', apiUrl);
    await store.set('api_key', apiKey);
    await store.save();
    await invoke('set_api_url', { url: apiUrl });
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <form onSubmit={onSave} style={{ display: 'grid', gap: 8, maxWidth: 540 }}>
      <label>
        API URL
        <input value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} style={{ width: '100%' }} />
      </label>
      <label>
        API Key
        <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ width: '100%' }} />
      </label>
      <button type="submit">Сохранить</button>
      {saved && <span style={{ color: 'green' }}>Сохранено</span>}
    </form>
  );
}
