//! Keep one embedded Python runtime per app instead of extracting it per IPC.
use std::{collections::HashMap, io::{BufRead, BufReader, Write}, path::PathBuf, process::{Child, ChildStdin, Command, Stdio}, sync::{mpsc, Arc, Mutex}, thread};
use serde_json::{json, Value};
type Reply = Result<Value, String>;
type Pending = Arc<Mutex<HashMap<u64, mpsc::Sender<Reply>>>>;
#[derive(Default)]
pub struct Engine(Mutex<Option<Session>>);
struct Session { child: Option<Child>, input: Option<ChildStdin>, pending: Pending, next: u64 }
impl Drop for Session {
    fn drop(&mut self) {
        // EOF asks Python to finish accepted requests/jobs, then clean up its
        // one-file extraction. Do not kill an in-flight export on app close.
        self.input.take();
        if let Some(mut child)=self.child.take() { thread::spawn(move || { let _=child.wait(); }); }
    }
}
impl Engine {
    pub fn request(&self, profile: Option<PathBuf>, legacy: Option<PathBuf>, request: Value) -> Reply {
        let (send, receive) = mpsc::channel();
        {
            let mut engine = self.0.lock().map_err(|_| "Python 引擎锁不可用")?;
            let dead = engine.as_mut().map(|s| s.child.as_mut().unwrap().try_wait().map(|s| s.is_some()).unwrap_or(true)).unwrap_or(true);
            if dead { *engine = Some(Session::start(profile, legacy)?); }
            let session = engine.as_mut().unwrap();
            session.next += 1;
            let id = session.next;
            session.pending.lock().map_err(|_| "Python 请求队列不可用")?.insert(id, send);
            let encoded = json!({"id":id,"request":request}).to_string() + "\n";
            if let Err(error) = session.input.as_mut().unwrap().write_all(encoded.as_bytes()) {
                session.pending.lock().unwrap().remove(&id);
                *engine = None;
                return Err(format!("Python 引擎连接中断，请重试：{error}"));
            }
        }
        receive.recv().map_err(|_| "Python 引擎连接已关闭，请重试".to_string())?
    }
}
impl Session {
    fn start(profile: Option<PathBuf>, legacy: Option<PathBuf>) -> Result<Self, String> {
        let mut command = if tauri::is_dev() {
            let mut c = Command::new(std::env::var("RESEARCH_V3_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() }));
            c.arg(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../python/bridge.py")); c
        } else {
            let executable = std::env::current_exe().map_err(|e|e.to_string())?;
            Command::new(executable.parent().ok_or("应用目录不可用")?.join(if cfg!(windows) {"research-python.exe"} else {"research-python"}))
        };
        command.arg("--serve");
        if let Some(path) = profile { command.env("RESEARCH_V3_PROFILE",path); } else { command.env_remove("RESEARCH_V3_PROFILE"); }
        if let Some(path) = legacy { command.env("RESEARCH_V3_LEGACY_PROFILE",path); } else { command.env_remove("RESEARCH_V3_LEGACY_PROFILE"); }
        command.env("MPLBACKEND","Agg").env("PYTHONUTF8","1").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
        let mut child = command.spawn().map_err(|e|format!("Python 引擎无法启动：{e}"))?;
        let input = child.stdin.take().ok_or("无法连接 Python 引擎")?;
        let output = child.stdout.take().ok_or("无法读取 Python 引擎")?;
        // Always drain diagnostics, including in a Windows GUI app without a console.
        if let Some(mut error) = child.stderr.take() { thread::spawn(move || { let _ = std::io::copy(&mut error, &mut std::io::sink()); }); }
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let replies = pending.clone();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let message = match line.ok().and_then(|line|serde_json::from_str::<Value>(&line).ok()) { Some(value)=>value, None=>break };
                if let Some(id) = message["id"].as_u64() {
                    if let Some(send) = replies.lock().unwrap().remove(&id) { let _ = send.send(Ok(message["response"].clone())); }
                }
            }
            for (_,send) in replies.lock().unwrap().drain() { let _ = send.send(Err("Python 引擎意外退出，请重试。".into())); }
        });
        Ok(Self { child:Some(child), input:Some(input), pending, next:0 })
    }
}
