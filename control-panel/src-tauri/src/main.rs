// Bunny OS Control Panel — native shell.
//
// The window loads the dependency-free web UI from ../ui. All privileged work
// is delegated to bunny-sessiond over its unix socket; this process never runs
// as root and never evaluates shell strings.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use serde_json::Value;

#[tauri::command]
async fn bunny_call(cmd: String, args: Option<Value>) -> Result<Value, String> {
    let args = args.unwrap_or_else(|| Value::Object(serde_json::Map::new()));
    tauri::async_runtime::spawn_blocking(move || commands::SessionClient::new().call(&cmd, args))
        .await
        .map_err(|err| format!("panel task failed: {err}"))?
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![bunny_call])
        .run(tauri::generate_context!())
        .expect("failed to start the Bunny OS Control Panel");
}
