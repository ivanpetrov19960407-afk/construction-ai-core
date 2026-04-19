#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use dirs::config_dir;
use std::{fs, path::PathBuf};
use tauri_plugin_store::{StoreExt, JsonValue};

const STORE_DIR: &str = "construction-ai";
const STORE_FILE: &str = "settings.json";
const API_URL_KEY: &str = "api_url";
const API_KEY_KEY: &str = "api_key";
const DEFAULT_API_URL: &str = "https://vanekpetrov1997.fvds.ru";

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

fn main() {
  tauri::Builder::default()
    .plugin(tauri_plugin_store::Builder::default().build())
    .setup(|app| {
      ensure_store_defaults(&app.handle())
        .map_err(|e| -> Box<dyn std::error::Error> { e.into() })?;
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![get_api_url, set_api_url, pick_pdf_file, read_pdf_file_bytes])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
