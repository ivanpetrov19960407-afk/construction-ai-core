const tg = window.Telegram?.WebApp;
const queryParams = new URLSearchParams(window.location.search);
const webApiKey = queryParams.get("api_key") || "";
const authToken = window.localStorage.getItem("auth_token") || "";
const apiKey = webApiKey || window.localStorage.getItem("api_key") || "";
const currentOrgId =
  queryParams.get("org_id") || window.localStorage.getItem("org_id") || "default";
const VAPID_PUBLIC_KEY =
  window.__VAPID_PUBLIC_KEY__ ||
  document.querySelector('meta[name="vapid-public-key"]')?.getAttribute("content") ||
  "";

function buildAuthHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  } else if (webApiKey) {
    headers["X-API-Key"] = webApiKey;
  }
  return headers;
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

async function subscribeToPush() {
  if (!("PushManager" in window) || !VAPID_PUBLIC_KEY || !apiKey) return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
  });
  await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ subscription: sub.toJSON(), org_id: currentOrgId }),
  });
}

if (tg) {
  tg.ready();
}

const theme = tg?.colorScheme || "light";
document.documentElement.dataset.theme = theme;
const themeIndicator = document.getElementById("theme-indicator");
if (themeIndicator) {
  themeIndicator.textContent = `Тема: ${theme}`;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/web/sw.js")
      .then(() => subscribeToPush().catch((error) => console.warn("Push subscription failed", error)))
      .catch((error) => {
        console.error("Service Worker registration failed:", error);
      });
  });
}

async function initBranding() {
  try {
    const response = await fetch("/api/branding", {
      method: "GET",
      headers: buildAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const branding = await response.json();
    document.documentElement.style.setProperty("--color-primary", branding.primary_color);
    document.documentElement.style.setProperty("--color-accent", branding.accent_color);

    const titleNode = document.getElementById("app-title");
    if (titleNode) {
      titleNode.textContent = branding.company_name || "Construction AI";
    }
    document.title = branding.company_name || "Construction AI";
  } catch (error) {
    console.warn("Branding fetch failed", error);
  }
}

async function initChatProbe() {
  try {
    await fetch("/api/chat", {
      method: "GET",
      headers: buildAuthHeaders(),
    });
  } catch (error) {
    console.warn("Chat probe failed", error);
  }
}

initBranding();
initChatProbe();

const tabButtons = document.querySelectorAll(".tab-btn");
const tabSections = document.querySelectorAll(".tab-section");

for (const button of tabButtons) {
  button.addEventListener("click", () => {
    const target = button.dataset.target;
    tabButtons.forEach((btn) => btn.classList.remove("active"));
    tabSections.forEach((section) => section.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(target)?.classList.add("active");
  });
}

const tkForm = document.getElementById("tk-form");
const tkResult = document.getElementById("tk-result");
const tkDownload = document.getElementById("tk-download");

if (tkForm) {
  tkForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const formData = new FormData(tkForm);
    const payload = {
      work_type: formData.get("work_type"),
      object_name: formData.get("object_name"),
      volume: formData.get("volume"),
      unit: formData.get("unit"),
    };

    tkResult.textContent = "Генерация...";
    tkDownload.hidden = true;

    try {
      const response = await fetch("/api/generate/tk", {
        method: "POST",
        headers: {
          ...buildAuthHeaders({
            "Content-Type": "application/json",
          }),
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      tkResult.textContent = JSON.stringify(data, null, 2);

      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      tkDownload.href = url;
      tkDownload.download = "tk-result.json";
      tkDownload.hidden = false;
    } catch (error) {
      tkResult.textContent = `Ошибка: ${error.message}`;
    }
  });
}
