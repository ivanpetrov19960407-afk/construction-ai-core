import { useEffect, useState } from "react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { getApiConfig, getQuotas } from "../api/coreClient";
import type { BillingQuotaResponse } from "../types/api";
import { colors, spacing } from "../styles/tokens";

export default function BillingPage() {
  const [data, setData] = useState<BillingQuotaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const response = await getQuotas(apiUrl, apiKey);
      setData(response);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Не удалось загрузить квоты.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <Card>
      <h2 style={{ marginTop: 0 }}>Биллинг</h2>
      <p style={{ marginTop: 0, color: colors.textSecondary }}>
        Главная / Админ / Биллинг
      </p>
      <Button type="button" onClick={() => void load()} loading={loading}>
        {loading ? "Обновление..." : "Обновить квоты"}
      </Button>
      {error && <p style={{ color: colors.error }}>{error}</p>}
      {data && (
        <div style={{ marginTop: spacing.md }}>
          <p>
            <strong>Тариф:</strong> {data.plan ?? "—"}
          </p>
          <p>
            <strong>Остаток:</strong> {data.remaining_quota ?? 0}
          </p>
          <p>
            <strong>Использовано:</strong> {data.used_quota ?? 0}
          </p>
          <p>
            <strong>Сброс:</strong> {data.reset_at ?? "—"}
          </p>
          <h3>История</h3>
          <ul>
            {(data.history ?? []).map((item) => (
              <li key={item.id}>
                {item.created_at}: {item.action} ({item.amount})
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
