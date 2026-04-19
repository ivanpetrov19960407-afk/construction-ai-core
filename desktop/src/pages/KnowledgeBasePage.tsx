import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import TabLayout, { type TabItem } from "../components/TabLayout";
import {
  deleteGlobalSource,
  ForbiddenError,
  getApiConfig,
  ingestGlobal,
  listGlobalSources,
  listMySources,
  uploadChatDocument,
  type RagSourceItem,
} from "../api/coreClient";
import { useAuth } from "../context/AuthContext";
import { colors, spacing } from "../styles/tokens";

type Mode = "my" | "global";

const roleBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  borderRadius: 999,
  border: `1px solid ${colors.border}`,
  padding: "4px 10px",
  fontSize: 13,
  color: colors.textSecondary,
} as const;

export default function KnowledgeBasePage() {
  const { isAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<Mode>("my");
  const [mySources, setMySources] = useState<RagSourceItem[]>([]);
  const [globalSources, setGlobalSources] = useState<RagSourceItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<
    "success" | "warning" | "error"
  >("success");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!isAdmin) {
      setActiveTab("my");
    }
  }, [isAdmin]);

  const loadSources = async () => {
    setIsLoading(true);
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      const mine = await listMySources(apiUrl, apiKey);
      setMySources(mine);

      if (isAdmin) {
        const global = await listGlobalSources(apiUrl, apiKey);
        setGlobalSources(global);
      } else {
        setGlobalSources([]);
      }
      setMessage("");
    } catch (error) {
      setMessageTone("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "Не удалось загрузить источники базы знаний.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSources();
  }, [isAdmin]);

  const onSelectFile = () => {
    fileInputRef.current?.click();
  };

  const onUpload = async (file: File) => {
    setIsUploading(true);
    setMessage("");
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      if (activeTab === "global") {
        await ingestGlobal(apiUrl, apiKey, { file, sourceName: file.name });
      } else {
        const sessionId = `kb-${crypto.randomUUID()}`;
        await uploadChatDocument(apiUrl, apiKey, { file, sessionId });
      }
      await loadSources();
      setMessageTone("success");
      setMessage(`Файл «${file.name}» загружен.`);
    } catch (error) {
      setMessageTone("error");
      if (error instanceof ForbiddenError) {
        setMessage(error.message);
      } else {
        setMessage(
          error instanceof Error ? error.message : "Ошибка загрузки файла.",
        );
      }
    } finally {
      setIsUploading(false);
    }
  };

  const onFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    await onUpload(file);
    event.target.value = "";
  };

  const onDeleteSource = async (source: string) => {
    try {
      const { apiUrl, apiKey } = await getApiConfig();
      await deleteGlobalSource(apiUrl, apiKey, source);
      await loadSources();
      setMessageTone("success");
      setMessage(`Источник «${source}» удалён.`);
    } catch (error) {
      setMessageTone("error");
      setMessage(
        error instanceof Error ? error.message : "Не удалось удалить источник.",
      );
    }
  };

  const renderTable = (sources: RagSourceItem[], allowDelete: boolean) => {
    if (isLoading) {
      return <p style={{ margin: 0 }}>Загрузка списка документов…</p>;
    }

    if (!sources.length) {
      return (
        <p style={{ margin: 0, color: colors.warning }}>
          Источники ещё не загружены.
        </p>
      );
    }

    return (
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th
              style={{
                textAlign: "left",
                borderBottom: `1px solid ${colors.border}`,
                paddingBottom: spacing.xs,
              }}
            >
              Источник
            </th>
            <th
              style={{
                textAlign: "left",
                borderBottom: `1px solid ${colors.border}`,
                paddingBottom: spacing.xs,
              }}
            >
              Чанков
            </th>
            {allowDelete && (
              <th
                style={{
                  textAlign: "left",
                  borderBottom: `1px solid ${colors.border}`,
                  paddingBottom: spacing.xs,
                }}
              >
                Действия
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.source}>
              <td style={{ paddingTop: spacing.xs }}>{source.source}</td>
              <td style={{ paddingTop: spacing.xs }}>{source.chunks}</td>
              {allowDelete && (
                <td style={{ paddingTop: spacing.xs }}>
                  <Button
                    variant="ghost"
                    onClick={() => onDeleteSource(source.source)}
                  >
                    Удалить источник
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const tabs = useMemo<TabItem[]>(() => {
    const base: TabItem[] = [
      {
        key: "my",
        title: "Моя база",
        content: renderTable(mySources, false),
      },
    ];
    if (isAdmin) {
      base.push({
        key: "global",
        title: "Глобальная база",
        content: renderTable(globalSources, true),
      });
    }
    return base;
  }, [globalSources, isAdmin, isLoading, mySources]);

  return (
    <Card>
      <div style={{ display: "grid", gap: spacing.md }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: spacing.sm,
          }}
        >
          <h2 style={{ margin: 0 }}>База знаний (KB)</h2>
          <span style={roleBadgeStyle}>
            Режим: {isAdmin ? "Администратор" : "ПТО-инженер"}
          </span>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: spacing.sm,
            flexWrap: "wrap",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx"
            style={{ display: "none" }}
            onChange={onFileChange}
          />
          <Button
            onClick={onSelectFile}
            disabled={isUploading || (activeTab === "global" && !isAdmin)}
            loading={isUploading}
          >
            {isUploading ? "Загрузка..." : "Загрузить файл"}
          </Button>
        </div>

        {message && (
          <p
            style={{
              margin: 0,
              color:
                messageTone === "success"
                  ? colors.success
                  : messageTone === "warning"
                    ? colors.warning
                    : colors.error,
            }}
          >
            {message}
          </p>
        )}

        <TabLayout
          tabs={tabs}
          activeTab={activeTab}
          onChange={(tab) => setActiveTab(tab as Mode)}
        />
      </div>
    </Card>
  );
}
