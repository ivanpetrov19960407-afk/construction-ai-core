import { appLogDir } from "@tauri-apps/api/path";

export type LogLevel = "info" | "warn" | "error";

export function logEvent(
  level: LogLevel,
  event: string,
  payload?: Record<string, unknown>,
) {
  const message = `[desktop] ${event}`;
  if (level === "error") {
    console.error(message, payload ?? {});
    return;
  }
  if (level === "warn") {
    console.warn(message, payload ?? {});
    return;
  }
  console.info(message, payload ?? {});
}

export function logError(event: string, payload?: Record<string, unknown>) {
  logEvent("error", event, payload);
}

export async function getAppLogDir() {
  return appLogDir();
}
