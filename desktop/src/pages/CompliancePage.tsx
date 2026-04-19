import { useEffect, useState } from "react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Input from "../components/ui/Input";
import {
  checkCompliance,
  getApiConfig,
  listCompliance,
} from "../api/coreClient";
import type { ComplianceCheckResponse, ComplianceRule } from "../types/api";
import { colors, spacing } from "../styles/tokens";

export default function CompliancePage() {
  const [rules, setRules] = useState<ComplianceRule[]>([]);
  const [projectId, setProjectId] = useState("");
  const [result, setResult] = useState<ComplianceCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadRules = async () => {
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await listCompliance(apiUrl, apiKey);
      setRules(response);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Не удалось загрузить нормативы.",
      );
    }
  };

  useEffect(() => {
    void loadRules();
  }, []);

  const onCheck = async () => {
    if (!projectId.trim()) {
      setError("Укажите ID проекта для проверки.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await checkCompliance(apiUrl, apiKey, {
        project_id: projectId.trim(),
        requirement_ids: rules.slice(0, 20).map((rule) => rule.id),
      });
      setResult(response);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Ошибка проверки соответствия.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Compliance / Соответствие</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>
        Главная / Админ / Compliance
      </p>
      <Input
        label="ID проекта"
        value={projectId}
        onChange={(e) => setProjectId(e.target.value)}
      />
      <Button
        type="button"
        onClick={onCheck}
        loading={loading}
        style={{ marginTop: spacing.sm }}
      >
        {loading ? "Проверка..." : "Проверить проект"}
      </Button>
      {error && <p style={{ color: colors.error }}>{error}</p>}
      <h3 style={{ marginBottom: spacing.xs }}>Индекс требований СП/ГОСТ</h3>
      <div
        style={{
          maxHeight: 200,
          overflowY: "auto",
          border: `1px solid ${colors.border}`,
          borderRadius: 8,
          padding: spacing.sm,
        }}
      >
        {rules.map((rule) => (
          <p key={rule.id} style={{ margin: 0, marginBottom: spacing.xs }}>
            {rule.code} — {rule.title}
          </p>
        ))}
        {rules.length === 0 && (
          <p style={{ margin: 0, color: colors.textSecondary }}>
            Пока нет данных.
          </p>
        )}
      </div>
      {result && (
        <Input
          type="textarea"
          label="Результат проверки"
          rows={10}
          readOnly
          value={JSON.stringify(result, null, 2)}
          style={{ marginTop: spacing.md }}
        />
      )}
    </Card>
  );
}
