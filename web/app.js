const tg = window.Telegram?.WebApp;
const queryParams = new URLSearchParams(window.location.search);
const webApiKey = queryParams.get("api_key") || "";
const authToken = window.localStorage.getItem("auth_token") || "";

function buildAuthHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  } else if (webApiKey) {
    headers["X-API-Key"] = webApiKey;
  }
  return headers;
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
    navigator.serviceWorker.register("/web/sw.js").catch((error) => {
      console.error("Service Worker registration failed:", error);
    });
  });
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
