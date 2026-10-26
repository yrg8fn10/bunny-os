//! Thin, auditable client for `bunny-sessiond`.
//!
//! The native shell exists so the panel can talk to the daemon without
//! exposing an HTTP port. It is still just a client: the daemon performs the
//! peer-credential check and re-authorises every privileged command.

use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::time::Duration;

const DEFAULT_SOCKET: &str = "/run/bunny/sessiond.sock";

/// Mirrors the command vocabulary in `system/bin/bunny-panel-bridge`.
/// Anything outside this list is rejected before a socket is even opened.
const ALLOWED: &[&str] = &[
    "ping",
    "status",
    "get-settings",
    "set-settings",
    "set-mode",
    "switch-mode",
    "launch",
    "library",
    "agent",
    "input-agent",
    "power",
    "update",
    "installer",
    "audit-tail",
    "help",
];

pub struct SessionClient {
    socket: PathBuf,
}

impl SessionClient {
    pub fn new() -> Self {
        let socket = std::env::var_os("BUNNY_SOCKET")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(DEFAULT_SOCKET));
        Self { socket }
    }

    pub fn call(&self, cmd: &str, args: Value) -> Result<Value, String> {
        if !ALLOWED.contains(&cmd) {
            return Err(format!("command not bridged: {cmd}"));
        }
        if !args.is_object() {
            return Err("args must be a JSON object".to_string());
        }

        let mut stream = UnixStream::connect(&self.socket).map_err(|err| {
            format!(
                "bunny-sessiond is unavailable at {}: {err}",
                self.socket.display()
            )
        })?;
        let _ = stream.set_write_timeout(Some(Duration::from_secs(5)));
        let _ = stream.set_read_timeout(Some(Duration::from_secs(35)));

        let request = json!({ "id": 1, "cmd": cmd, "args": args });
        let mut payload = serde_json::to_vec(&request).map_err(|err| err.to_string())?;
        payload.push(b'\n');
        stream
            .write_all(&payload)
            .and_then(|_| stream.flush())
            .map_err(|err| format!("write failed: {err}"))?;

        let mut reader = BufReader::new(stream);
        let mut line = String::new();
        reader
            .read_line(&mut line)
            .map_err(|err| format!("read failed: {err}"))?;
        if line.trim().is_empty() {
            return Err("bunny-sessiond closed the connection".to_string());
        }

        let reply: Value =
            serde_json::from_str(&line).map_err(|err| format!("invalid daemon reply: {err}"))?;
        if reply.get("ok").and_then(Value::as_bool) == Some(true) {
            Ok(reply.get("result").cloned().unwrap_or(Value::Null))
        } else {
            Err(reply
                .get("error")
                .and_then(Value::as_str)
                .unwrap_or("daemon rejected the command")
                .to_string())
        }
    }
}
