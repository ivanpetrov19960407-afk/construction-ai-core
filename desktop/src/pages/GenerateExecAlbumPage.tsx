import { type FormEvent, useState } from "react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import ErrorModal from "../components/ErrorModal";
import Input from "../components/ui/Input";
import {
  generateExecAlbum,
  getApiConfig,
  SSEError,
  type GenerationStage,
} from "../api/coreClient";
import { colors, spacing } from "../styles/tokens";

export default function GenerateExecAlbumPage() {
  const [projectId, setProjectId] = useState("");
  const [workItemsRaw, setWorkItemsRaw] = useState("");
  const [result, setResult] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<GenerationStage>("queued");
  const [error, setError] = useState("");
  const [sseError, setSseError] = useState<SSEError | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const workItems = workItemsRaw
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);

    if (!projectId.trim() || workItems.length === 0) {
      setError("Укажите проект и хотя бы один вид работ.");
      return;
    }

    setIsLoading(true);
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await generateExecAlbum(
        apiUrl,
        apiKey,
        { project_id: projectId.trim(), work_items: workItems },
        (streamEvent) => {
          setProgress(streamEvent.progress ?? 0);
          setStage(streamEvent.stage);
        },
      );
      const output =
        response.result ??
        response.text ??
        response.content ??
        JSON.stringify(response, null, 2);
      setResult(
        typeof output === "string" ? output : JSON.stringify(output, null, 2),
      );
    } catch (submitError) {
      if (submitError instanceof SSEError) {
        setSseError(submitError);
      }
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Ошибка генерации исполнительного альбома.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const onDownload = () => {
    if (!result) return;
    const blob = new Blob([result], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `exec-album-${Date.now()}.zip`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Исполнительный альбом</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>
        Главная / Генерация / Исполнительный альбом
      </p>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: spacing.md }}>
        <Input
          label="ID проекта"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        />
        <Input
          type="textarea"
          label="Перечень работ (каждая работа с новой строки)"
          rows={8}
          value={workItemsRaw}
          onChange={(e) => setWorkItemsRaw(e.target.value)}
        />
        <Button type="submit" loading={isLoading}>
          {isLoading ? "Генерация..." : "Сгенерировать"}
        </Button>
      </form>
      {isLoading && (
        <div style={{ marginTop: spacing.md }}>
          <div
            style={{ color: colors.textSecondary, marginBottom: spacing.xs }}
          >
            Шаг: {stage}
          </div>
          <div
            style={{
              width: "100%",
              height: 8,
              background: "#e5e7eb",
              borderRadius: 999,
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: 8,
                background: colors.primary,
                borderRadius: 999,
              }}
            />
          </div>
        </div>
      )}
      {error && <p style={{ color: colors.error }}>{error}</p>}
      {result && (
        <div style={{ marginTop: spacing.md }}>
          <Input
            type="textarea"
            label="Результат"
            rows={12}
            value={result}
            readOnly
          />
          <Button
            type="button"
            onClick={onDownload}
            style={{ marginTop: spacing.sm }}
          >
            Скачать ZIP
          </Button>
        </div>
      )}
      <ErrorModal
        isOpen={Boolean(sseError)}
        onClose={() => setSseError(null)}
        title={sseError?.message ?? "Ошибка"}
        details={sseError?.details}
      />
    </Card>
  );
}
