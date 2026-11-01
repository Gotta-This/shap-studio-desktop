#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{Read, Write}, path::PathBuf, process::{Command,Stdio}, sync::{Arc,atomic::{AtomicUsize,Ordering}}};
use tauri::{Manager,Emitter};
#[derive(Clone,Default)]
struct Running(Arc<AtomicUsize>);
struct CountGuard(Arc<AtomicUsize>);
impl Drop for CountGuard { fn drop(&mut self) { self.0.fetch_sub(1,Ordering::SeqCst); } }

// Use Tauri's environment: its CLI enables tauri/custom-protocol directly;
// that does not imply our similarly named crate feature is enabled.
fn request_engine(profile: PathBuf, request: serde_json::Value) -> Result<serde_json::Value,String> {
    let mut command;
    if tauri::is_dev() {
        let python=std::env::var("RESEARCH_V3_PYTHON").unwrap_or_else(|_| if cfg!(windows){"python".into()}else{"python3".into()});
        command=Command::new(python);
        command.arg(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../python/bridge.py"));
    } else {
        let exe=std::env::current_exe().map_err(|e|e.to_string())?;
        let parent=exe.parent().ok_or("应用目录不可用")?;
        command=Command::new(parent.join(if cfg!(windows){"research-python.exe"}else{"research-python"}));
    }
    command.env("RESEARCH_V3_PROFILE",profile).env("MPLBACKEND","Agg").env("PYTHONUTF8","1").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)] { use std::os::windows::process::CommandExt;command.creation_flags(0x08000000); }
    let mut child=command.spawn().map_err(|e|format!("Python 引擎无法启动：{e}"))?;
    let mut input=child.stdin.take().ok_or("无法连接 Python 引擎")?;
    input.write_all(request.to_string().as_bytes()).map_err(|e|e.to_string())?;drop(input);
    let output=child.wait_with_output().map_err(|e|e.to_string())?;
    serde_json::from_slice(&output.stdout).map_err(|_|format!("Python 引擎未返回有效结果（{}）：{}",output.status,String::from_utf8_lossy(&output.stderr).chars().rev().take(500).collect::<String>().chars().rev().collect::<String>()))
}
#[tauri::command]
async fn python_request(app:tauri::AppHandle, request:serde_json::Value, running:tauri::State<'_,Running>) -> Result<serde_json::Value,String> {
    running.0.fetch_add(1,Ordering::SeqCst);
    let count=CountGuard(running.0.clone());
    tauri::async_runtime::spawn_blocking(move || {
        let _guard=count;
        let profile=match std::env::var_os("RESEARCH_V3_PROFILE") { Some(p)=>PathBuf::from(p),None=>app.path().app_data_dir().map_err(|e|e.to_string())? };
        request_engine(profile,request)
    }).await.map_err(|e|e.to_string())?
}
fn main() {
    // Exercise the exact production bridge before constructing any window.
    // Used by installed-package tests; never needs a desktop or OS input.
    let args:Vec<_>=std::env::args_os().collect();
    if args.get(1).is_some_and(|arg|arg=="--bridge-request") {
        let result=(|| {
            let profile=PathBuf::from(args.get(2).ok_or("缺少测试配置目录")?);
            if !profile.is_absolute() { return Err("测试配置目录必须是绝对路径".into()); }
            let mut input=String::new();std::io::stdin().read_to_string(&mut input).map_err(|e|e.to_string())?;
            let request=serde_json::from_str(&input).map_err(|e|e.to_string())?;
            request_engine(profile,request)
        })();
        match result {
            Ok(value)=>println!("{}",value),
            Err(error)=>{ println!("{}",serde_json::json!({"ok":false,"error":error}));std::process::exit(1); }
        }
        return;
    }
    tauri::Builder::default().manage(Running::default()).plugin(tauri_plugin_dialog::init()).plugin(tauri_plugin_opener::init())
      .setup(|app| { if std::env::var("RESEARCH_V3_DEBUG").as_deref()==Ok("1") { if let Some(window)=app.get_webview_window("main") { eprintln!("V3 URL: {:?}",window.url()); #[cfg(debug_assertions)] window.open_devtools(); } } Ok(()) })
      .invoke_handler(tauri::generate_handler![python_request])
      .on_window_event(|window,event| { if let tauri::WindowEvent::CloseRequested{api,..}=event { if window.state::<Running>().0.load(Ordering::SeqCst)>0 { api.prevent_close();let _=window.emit("close-blocked",()); } } })
      .run(tauri::generate_context!()).expect("启动科研数据工具集失败");
}
