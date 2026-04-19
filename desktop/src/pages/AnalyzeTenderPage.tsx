import { useState } from "react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import { analyzeDocument, getApiConfig } from "../api/coreClient";
import { colors, spacing } from "../styles/tokens";

export default function AnalyzeTenderPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState("");
  const [requirements, setRequirements] = useState<string[]>([]);
  const [risks, setRisks] = useState<string[]>([]);
  const [deadlines, setDeadlines] = useState<string[]>([]);
  const [estimate, setEstimate] = useState("");

  const onAnalyze = async () => {
    if (!file) {
      setError("Перетащите PDF/ZIP или выберите файл.");
      return;
    }
    setError("");
    setIsLoading(true);

    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await analyzeDocument(apiUrl, apiKey, file);
      const payload = response as Record<string, unknown>;
      setSummary(String(payload.summary ?? payload.result ?? ""));
      setRequirements(
        Array.isArray(payload.requirements)
          ? payload.requirements.map(String)
          : [],
      );
      setRisks(Array.isArray(payload.risks) ? payload.risks.map(String) : []);
      setDeadlines(
        Array.isArray(payload.deadlines) ? payload.deadlines.map(String) : [],
      );
      setEstimate(String(payload.estimated_budget ?? payload.estimate ?? ""));
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Ошибка анализа тендера.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Разбор тендера</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>
        Главная / Анализ / Тендер
      </p>
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const droppedFile = e.dataTransfer.files?.[0];
          if (droppedFile) setFile(droppedFile);
        }}
        style={{
          border: `1px dashed ${colors.border}`,
          borderRadius: 12,
          padding: spacing.lg,
          marginBottom: spacing.md,
        }}
      >
        <p style={{ marginTop: 0 }}>
          Drag-n-drop PDF/ZIP сюда или выберите вручную.
        </p>
        <input
          type="file"
          accept=".pdf,.zip"
          onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)}
        />
        {file && <p style={{ marginBottom: 0 }}>Файл: {file.name}</p>}
      </div>
      <Button type="button" onClick={onAnalyze} loading={isLoading}>
        {isLoading ? "Анализ..." : "Проанализировать"}
      </Button>
      {error && <p style={{ color: colors.error }}>{error}</p>}
      {summary && (
        <Input
          type="textarea"
          label="Краткое резюме"
          rows={8}
          value={summary}
          readOnly
          style={{ marginTop: spacing.md }}
        />
      )}
      {!!requirements.length && (
        <ul>
          {requirements.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {!!risks.length && (
        <ul>
          {risks.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {!!deadlines.length && (
        <ul>
          {deadlines.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {estimate && (
        <p>
          <strong>Сметная оценка:</strong> {estimate}
        </p>
      )}
    </Card>
  );
}
