#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use dirs::config_dir;
use log::{error, info, warn};
use std::{fs, path::PathBuf};
use tauri::Manager;
use tauri_plugin_log::{Target, TargetKind};
use tauri_plugin_store::{StoreExt, JsonValue};

const STORE_DIR: &str = "construction-ai";
const STORE_FILE: &str = "settings.json";
const API_URL_KEY: &str = "api_url";
const API_KEY_KEY: &str = "api_key";
const DEFAULT_API_URL: &str = "https://vanekpetrov1997.fvds.ru";
const LOGS_DIR_NAME: &str = "logs";
const LOG_FILE_NAME: &str = "app.log";

fn settings_path() -> PathBuf {
  config_dir()
    .unwrap_or_else(|| PathBuf::from("."))
    .join(STORE_DIR)
    .join(STORE_FILE)
}

#[tauri::command]
fn get_api_url(app: tauri::AppHandle) -> String {
  let path = settings_path();
  match app.store(path) {
    Ok(store) => store
      .get(API_URL_KEY)
      .and_then(|v| v.as_str().map(str::to_string))
      .unwrap_or_else(|| DEFAULT_API_URL.to_string()),
    Err(_) => DEFAULT_API_URL.to_string()
  }
}

#[tauri::command]
fn set_api_url(app: tauri::AppHandle, url: String) -> Result<(), String> {
  let path = settings_path();
  let store = app.store(path).map_err(|e| e.to_string())?;
  store.set(API_URL_KEY, JsonValue::String(url));
  info!("API URL updated in desktop settings");
  store.save().map_err(|e| e.to_string())
}

#[derive(serde::Serialize)]
struct PickedPdfFile {
  path: String,
  name: String,
  size: u64
}

#[tauri::command]
fn pick_pdf_file() -> Option<PickedPdfFile> {
  let file = rfd::FileDialog::new()
    .add_filter("PDF", &["pdf"])
    .pick_file()?;

  let metadata = fs::metadata(&file).ok()?;
  let name = file
    .file_name()
    .and_then(|n| n.to_str())
    .map(str::to_string)
    .unwrap_or_else(|| "document.pdf".to_string());

  Some(PickedPdfFile {
    path: file.display().to_string(),
    name,
    size: metadata.len()
  })
}

#[tauri::command]
fn read_pdf_file_bytes(path: String) -> Result<Vec<u8>, String> {
  fs::read(path).map_err(|e| e.to_string())
}

fn app_logs_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
  app
    .path()
    .app_data_dir()
    .map_err(|e| e.to_string())
    .map(|path| path.join(LOGS_DIR_NAME))
}

fn app_log_file(app: &tauri::AppHandle) -> Result<PathBuf, String> {
  app_logs_dir(app).map(|dir| dir.join(LOG_FILE_NAME))
}

#[tauri::command]
fn open_logs_folder(app: tauri::AppHandle) -> Result<(), String> {
  let logs_dir = app_logs_dir(&app)?;
  fs::create_dir_all(&logs_dir).map_err(|e| e.to_string())?;

  #[cfg(target_os = "windows")]
  let mut command = {
    let mut cmd = std::process::Command::new("explorer");
    cmd.arg(&logs_dir);
    cmd
  };

  #[cfg(target_os = "macos")]
  let mut command = {
    let mut cmd = std::process::Command::new("open");
    cmd.arg(&logs_dir);
    cmd
  };

  #[cfg(all(unix, not(target_os = "macos")))]
  let mut command = {
    let mut cmd = std::process::Command::new("xdg-open");
    cmd.arg(&logs_dir);
    cmd
  };

  command.status().map_err(|e| e.to_string())?;
  info!("Logs directory opened: {}", logs_dir.display());
  Ok(())
}

#[tauri::command]
fn copy_last_log_lines(app: tauri::AppHandle, lines: Option<usize>) -> Result<String, String> {
  let log_path = app_log_file(&app)?;
  let line_limit = lines.unwrap_or(200).max(1);

  if !log_path.exists() {
    warn!("Log file not found yet: {}", log_path.display());
    return Ok(String::new());
  }

  let content = fs::read_to_string(&log_path).map_err(|e| e.to_string())?;
  let mut log_lines = content.lines().collect::<Vec<_>>();
  let start = log_lines.len().saturating_sub(line_limit);
  let tail = log_lines.drain(start..).collect::<Vec<_>>().join("\n");

  info!(
    "Read {} lines from app log for diagnostics copy action",
    line_limit
  );

  Ok(tail)
}

fn ensure_store_defaults(app: &tauri::AppHandle) -> Result<(), String> {
  let path = settings_path();
  if let Some(parent) = path.parent() {
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
  }

  let store = app.store(path).map_err(|e| e.to_string())?;
  if store.get(API_URL_KEY).is_none() {
    store.set(API_URL_KEY, JsonValue::String(DEFAULT_API_URL.into()));
  }
  if store.get(API_KEY_KEY).is_none() {
    store.set(API_KEY_KEY, JsonValue::String(String::new()));
  }

  store.save().map_err(|e| e.to_string())
}

fn ensure_logs_dir(app: &tauri::AppHandle) -> Result<(), String> {
  let logs_dir = app_logs_dir(app)?;
  fs::create_dir_all(&logs_dir).map_err(|e| e.to_string())
}

fn main() {
  tauri::Builder::default()
    .plugin(
      tauri_plugin_log::Builder::default()
        .targets([
          Target::new(TargetKind::Stdout),
          Target::new(TargetKind::LogDir {
            file_name: Some(LOG_FILE_NAME.into())
          })
        ])
        .level(log::LevelFilter::Info)
        .build()
    )
    .plugin(tauri_plugin_store::Builder::default().build())
    .setup(|app| {
      ensure_logs_dir(&app.handle())
        .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
      ensure_store_defaults(&app.handle())
        .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
      info!("Desktop app initialized");
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
      get_api_url,
      set_api_url,
      pick_pdf_file,
      read_pdf_file_bytes,
      open_logs_folder,
      copy_last_log_lines
    ])
    .run(tauri::generate_context!())
    .unwrap_or_else(|error| {
      error!("Error while running tauri application: {}", error);
      panic!("error while running tauri application: {error}");
    });
}
