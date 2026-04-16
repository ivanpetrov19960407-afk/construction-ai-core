import { useEffect, useMemo, useState } from 'react';
import TabLayout from '../components/TabLayout';
import { getApiConfig } from '../api/coreClient';
import type { GSNChecklist, GSNSectionStatus, ScheduleForecast, SignStatus } from '../types/handover';

interface ProjectDocument {
  id: string;
  title: string;
  document_type: string;
  status?: SignStatus;
}

interface ProjectInfo {
  id: string;
  is_state_contract?: boolean;
}

const sectionOrder = ['AR', 'KZH', 'KM', 'OV', 'VK', 'EM'];

function normalizeForecast(payload: Partial<ScheduleForecast>): ScheduleForecast {
  return {
    predicted_completion: String(payload.predicted_completion ?? '—'),
    avg_delay_days: Number(payload.avg_delay_days ?? 0),
    delay_rate: Number(payload.delay_rate ?? 0),
    risks: Array.isArray(payload.risks) ? payload.risks : [],
    recommendations: Array.isArray(payload.recommendations) ? payload.recommendations : []
  };
}

export default function HandoverPage() {
  const [activeTab, setActiveTab] = useState('readiness');
  const [projectId, setProjectId] = useState('');
  const [userId, setUserId] = useState('');
  const [checklist, setChecklist] = useState<GSNChecklist | null>(null);
  const [forecast, setForecast] = useState<ScheduleForecast | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [signedDocIds, setSignedDocIds] = useState<string[]>([]);
  const [batchProgress, setBatchProgress] = useState<{ signed: number; total: number } | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const savedProjectId = window.localStorage.getItem('handover_project_id') ?? '';
    const savedUserId = window.localStorage.getItem('handover_user_id') ?? '';
    setProjectId(savedProjectId);
    setUserId(savedUserId);
  }, []);

  const fetchJson = async <T,>(endpoint: string, init?: RequestInit): Promise<T> => {
    const { apiUrl, apiKey } = await getApiConfig();
    const response = await fetch(`${apiUrl.replace(/\/$/, '')}${endpoint}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey,
        ...(init?.headers ?? {})
      }
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    return (await response.json()) as T;
  };

  const loadReadiness = async () => {
    const data = await fetchJson<GSNChecklist>(`/api/compliance/gsn-checklist/${encodeURIComponent(projectId)}`);
    setChecklist(data);
  };

  const loadSigning = async () => {
    const [projectResponse, docsResponse] = await Promise.all([
      fetchJson<ProjectInfo>(`/api/projects/${encodeURIComponent(projectId)}`),
      fetchJson<{ documents: ProjectDocument[] }>(`/api/projects/${encodeURIComponent(projectId)}/documents`)
    ]);
    setProject(projectResponse);
    setDocuments((docsResponse.documents || []).filter((doc) => (doc.status ?? 'approved') === 'approved'));
  };

  const loadForecast = async () => {
    const data = await fetchJson<Partial<ScheduleForecast>>(
      `/api/analytics/schedule/${encodeURIComponent(projectId)}`
    );
    setForecast(normalizeForecast(data));
  };

  const loadAll = async () => {
    if (!projectId.trim()) {
      setError('Укажите projectId');
      return;
    }

    setLoading(true);
    setError('');
    window.localStorage.setItem('handover_project_id', projectId);
    window.localStorage.setItem('handover_user_id', userId);

    try {
      await Promise.all([loadReadiness(), loadSigning(), loadForecast()]);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateReport = async () => {
    if (!projectId.trim()) {
      setError('Укажите projectId');
      return;
    }

    setError('');
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await fetch(
        `${apiUrl.replace(/\/$/, '')}/api/compliance/gsn-report/${encodeURIComponent(projectId)}`,
        {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        }
      );

      if (!response.ok) {
        throw new Error(`Report API error: ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `gsn_checklist_${projectId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reportError) {
      setError(reportError instanceof Error ? reportError.message : 'Ошибка формирования отчёта');
    }
  };

  const handleSign = async (doc: ProjectDocument) => {
    if (!userId.trim()) {
      setError('Укажите userId для ЭЦП');
      return;
    }

    setError('');
    try {
      await fetchJson('/api/sign/document', {
        method: 'POST',
        body: JSON.stringify({
          doc_id: doc.id,
          doc_type: doc.document_type,
          user_id: userId
        })
      });
      setSignedDocIds((prev) => [...new Set([...prev, doc.id])]);
    } catch (signError) {
      setError(signError instanceof Error ? signError.message : 'Ошибка подписи');
    }
  };

  const handleIsupSubmit = async (docId: string) => {
    setError('');
    try {
      await fetchJson('/api/isup/submit-document', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, doc_id: docId })
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ошибка передачи в ИСУП');
    }
  };

  const handleBatchSign = async () => {
    if (!userId.trim()) {
      setError('Укажите userId для ЭЦП');
      return;
    }

    const pendingDocuments = documents.filter((doc) => {
      const status: SignStatus = signedDocIds.includes(doc.id) ? 'signed' : doc.status ?? 'approved';
      return status !== 'signed';
    });

    if (!pendingDocuments.length) {
      setBatchProgress({ signed: 0, total: 0 });
      return;
    }

    const docsByType = pendingDocuments.reduce<Record<string, string[]>>((acc, doc) => {
      const type = doc.document_type;
      if (!acc[type]) acc[type] = [];
      acc[type].push(doc.id);
      return acc;
    }, {});

    setError('');
    setBatchLoading(true);
    setBatchProgress({ signed: 0, total: pendingDocuments.length });

    try {
      let signedTotal = 0;
      const newlySignedIds = new Set<string>();
      for (const [docType, ids] of Object.entries(docsByType)) {
        const response = await fetchJson<{ results: { doc_id: string; status: SignStatus }[] }>(
          '/api/sign/batch',
          {
            method: 'POST',
            body: JSON.stringify({
              doc_ids: ids,
              doc_type: docType,
              user_id: userId
            })
          }
        );
        for (const result of response.results ?? []) {
          if (result.status === 'signed') {
            signedTotal += 1;
            newlySignedIds.add(result.doc_id);
          }
        }
        setBatchProgress({ signed: signedTotal, total: pendingDocuments.length });
      }
      if (newlySignedIds.size > 0) {
        setSignedDocIds((prev) => [...new Set([...prev, ...Array.from(newlySignedIds)])]);
      }
    } catch (signError) {
      setError(signError instanceof Error ? signError.message : 'Ошибка пакетной подписи');
    } finally {
      setBatchLoading(false);
    }
  };

  const checklistSections = useMemo<GSNSectionStatus[]>(() => {
    if (!checklist) {
      return [];
    }
    return [...(checklist.sections ?? [])].sort(
      (a, b) => sectionOrder.indexOf(a.section) - sectionOrder.indexOf(b.section)
    );
  }, [checklist]);

  const riskLabel = (level: string) => {
    if (level === 'high') return { text: 'высокий', color: '#dc2626' };
    if (level === 'medium') return { text: 'средний', color: '#d97706' };
    return { text: 'низкий', color: '#16a34a' };
  };

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <h2>Сдача объекта</h2>

      <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>Project ID</span>
          <input value={projectId} onChange={(event) => setProjectId(event.target.value)} placeholder="UUID проекта" />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span>User ID для ЭЦП</span>
          <input value={userId} onChange={(event) => setUserId(event.target.value)} placeholder="Идентификатор пользователя" />
        </label>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={loadAll} disabled={loading}>
          {loading ? 'Загрузка...' : 'Загрузить данные'}
        </button>
        <button type="button" onClick={handleBatchSign} disabled={batchLoading || !documents.length}>
          {batchLoading ? 'Подписание...' : 'Подписать все (batch)'}
        </button>
      </div>
      {error && <p style={{ color: 'crimson', margin: 0 }}>{error}</p>}

      <TabLayout
        tabs={[
          {
            key: 'readiness',
            title: 'Готовность ИД',
            content: (
              <section style={{ display: 'grid', gap: 12 }}>
                <button type="button" onClick={handleGenerateReport}>
                  Сформировать отчёт
                </button>
                <div style={{ display: 'grid', gap: 10 }}>
                  {checklistSections.map((section) => (
                    <article
                      key={section.section}
                      style={{ border: '1px solid #33415555', borderRadius: 12, padding: 12, display: 'grid', gap: 8 }}
                    >
                      <strong>{section.section}</strong>
                      <div style={{ width: '100%', height: 10, borderRadius: 8, background: '#33415533' }}>
                        <div
                          style={{
                            width: `${Math.max(0, Math.min(100, section.completion_pct))}%`,
                            height: '100%',
                            borderRadius: 8,
                            background: '#2563eb'
                          }}
                        />
                      </div>
                      <small>Готовность: {section.completion_pct}%</small>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <div>
                          <strong style={{ color: '#dc2626' }}>Отсутствует</strong>
                          <ul>
                            {section.missing.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <strong style={{ color: '#16a34a' }}>В наличии</strong>
                          <ul>
                            {section.present.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )
          },
          {
            key: 'signing',
            title: 'Подписание документов',
            content: (
              <section style={{ display: 'grid', gap: 10 }}>
                {batchProgress && <p style={{ margin: 0 }}>Подписано {batchProgress.signed} / {batchProgress.total}</p>}
                {documents.map((doc) => {
                  const status: SignStatus = signedDocIds.includes(doc.id) ? 'signed' : doc.status ?? 'approved';
                  const icon = status === 'signed' ? '✅' : status === 'approved' ? '🟡' : '📝';
                  const title = status === 'signed' ? 'подписан' : status === 'approved' ? 'утверждён' : 'черновик';

                  return (
                    <article
                      key={doc.id}
                      style={{ border: '1px solid #33415555', borderRadius: 12, padding: 12, display: 'grid', gap: 8 }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                        <strong>{doc.title}</strong>
                        <span>
                          {icon} {title}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button type="button" onClick={() => handleSign(doc)} disabled={status === 'signed'}>
                          Подписать ЭЦП
                        </button>
                        {project?.is_state_contract && status === 'signed' && (
                          <button type="button" onClick={() => handleIsupSubmit(doc.id)}>
                            Передать в ИСУП
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
                {!documents.length && <p>Нет документов со статусом «утверждён».</p>}
              </section>
            )
          },
          {
            key: 'forecast',
            title: 'Прогноз завершения',
            content: (
              <section style={{ display: 'grid', gap: 10 }}>
                <article style={{ border: '1px solid #33415555', borderRadius: 12, padding: 12 }}>
                  <strong>Ожидаемая дата завершения: {forecast?.predicted_completion ?? '—'}</strong>
                  <p style={{ marginBottom: 6 }}>Средняя задержка: {forecast?.avg_delay_days ?? 0} дн.</p>
                  <p style={{ marginTop: 0 }}>Вероятность задержки: {((forecast?.delay_rate ?? 0) * 100).toFixed(1)}%</p>
                </article>
                <article style={{ border: '1px solid #33415555', borderRadius: 12, padding: 12 }}>
                  <strong>Риски</strong>
                  <ul>
                    {(forecast?.risks ?? []).map((risk) => {
                      const badge = riskLabel(risk.level);
                      return (
                        <li key={`${risk.title}-${risk.level}`}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: 999,
                              marginRight: 8,
                              background: `${badge.color}22`,
                              color: badge.color
                            }}
                          >
                            {badge.text}
                          </span>
                          <strong>{risk.title}</strong>
                          {risk.details ? ` — ${risk.details}` : ''}
                        </li>
                      );
                    })}
                  </ul>
                </article>
                <article style={{ border: '1px solid #33415555', borderRadius: 12, padding: 12 }}>
                  <strong>Рекомендации ИИ</strong>
                  <ul>
                    {(forecast?.recommendations ?? []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </article>
              </section>
            )
          }
        ]}
        activeTab={activeTab}
        onChange={setActiveTab}
      />
    </section>
  );
}
