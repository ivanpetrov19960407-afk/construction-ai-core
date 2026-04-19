import type { ChatSource } from '../api/coreClient';

interface Props {
  sources: ChatSource[];
}

export default function MessageSources({ sources }: Props) {
  if (!sources.length) return null;

  return (
    <div style={{ marginTop: 10, borderTop: '1px dashed #d1d5db', paddingTop: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: '#4b5563', marginBottom: 6 }}>
        Источники
      </div>
      <ul style={{ margin: 0, paddingInlineStart: 16, display: 'grid', gap: 4 }}>
        {sources.slice(0, 3).map((source, index) => (
          <li
            key={`${source.title}-${source.page}-${index}`}
            style={{ fontSize: 12, color: '#374151' }}
          >
            {source.title} · стр. {source.page || '—'} · релевантность{' '}
            {(source.score * 100).toFixed(0)}%
          </li>
        ))}
      </ul>
    </div>
  );
}
