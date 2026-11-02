#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{Read, Write}, path::PathBuf, process::{Command,Stdio}, sync::{Arc,atomic::{AtomicUsize,Ordering}}};
use tauri::{Manager,Emitter};
mod ui_review;
mod engine;
#[derive(Clone,Default)]
struct Running(Arc<AtomicUsize>);
struct CountGuard(Arc<AtomicUsize>);
impl Drop for CountGuard { fn drop(&mut self) { self.0.fetch_sub(1,Ordering::SeqCst); } }

// Use Tauri's environment: its CLI enables tauri/custom-protocol directly;
// that does not imply our similarly named crate feature is enabled.
fn request_engine(profile: Option<PathBuf>, legacy_profile: Option<PathBuf>, request: serde_json::Value) -> Result<serde_json::Value,String> {
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
    if let Some(profile)=profile { command.env("RESEARCH_V3_PROFILE",profile); } else { command.env_remove("RESEARCH_V3_PROFILE"); }
    if let Some(legacy)=legacy_profile { command.env("RESEARCH_V3_LEGACY_PROFILE",legacy); } else { command.env_remove("RESEARCH_V3_LEGACY_PROFILE"); }
    command.env("MPLBACKEND","Agg").env("PYTHONUTF8","1").stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)] { use std::os::windows::process::CommandExt;command.creation_flags(0x08000000); }
    let mut child=command.spawn().map_err(|e|format!("Python 引擎无法启动：{e}"))?;
    let mut input=child.stdin.take().ok_or("无法连接 Python 引擎")?;
    input.write_all(request.to_string().as_bytes()).map_err(|e|e.to_string())?;drop(input);
    let output=child.wait_with_output().map_err(|e|e.to_string())?;
    serde_json::from_slice(&output.stdout).map_err(|_|format!("Python 引擎未返回有效结果（{}）：{}",output.status,String::from_utf8_lossy(&output.stderr).chars().rev().take(500).collect::<String>().chars().rev().collect::<String>()))
}
#[tauri::command]
async fn python_request(app:tauri::AppHandle, request:serde_json::Value, running:tauri::State<'_,Running>, engine:tauri::State<'_,Arc<engine::Engine>>) -> Result<serde_json::Value,String> {
    let engine=engine.inner().clone();
    running.0.fetch_add(1,Ordering::SeqCst);
    let count=CountGuard(running.0.clone());
    tauri::async_runtime::spawn_blocking(move || {
        let _guard=count;
        let profile=std::env::var_os("RESEARCH_V3_PROFILE").map(PathBuf::from);
        let legacy=if ui_review::enabled() {None} else {app.path().app_data_dir().ok()};
        engine.request(profile,legacy,request)
    }).await.map_err(|e|e.to_string())?
}
fn main() {
    // Exercise the exact production bridge before constructing any window.
    // Used by installed-package tests; never needs a desktop or OS input.
    let args:Vec<_>=std::env::args_os().collect();
    if args.get(1).is_some_and(|arg|arg=="--bridge-request") {
        let result=(|| {
            let value=args.get(2).ok_or("缺少测试配置目录")?;
            let profile=if value=="-" { None } else { let path=PathBuf::from(value); if !path.is_absolute() {return Err("测试配置目录必须是绝对路径".into());} Some(path) };
            let mut input=String::new();std::io::stdin().read_to_string(&mut input).map_err(|e|e.to_string())?;
            let request=serde_json::from_str(&input).map_err(|e|e.to_string())?;
            request_engine(profile,None,request)
        })();
        match result {
            Ok(value)=>println!("{}",value),
            Err(error)=>{ println!("{}",serde_json::json!({"ok":false,"error":error}));std::process::exit(1); }
        }
        return;
    }
    if args.get(1).is_some_and(|arg|arg=="--bridge-service-host") {
        use std::io::BufRead;
        let engine=engine::Engine::default();
        let profile=std::env::var_os("RESEARCH_V3_PROFILE").map(PathBuf::from);
        for line in std::io::stdin().lock().lines() {
            let response=line.map_err(|e|e.to_string()).and_then(|line|serde_json::from_str(&line).map_err(|e|e.to_string())).and_then(|request|engine.request(profile.clone(),None,request));
            println!("{}",response.unwrap_or_else(|error|serde_json::json!({"ok":false,"error":error})));
        }
        return;
    }
    ui_review::initialize(&args);
    let mut context=tauri::generate_context!();
    if ui_review::enabled() { for window in &mut context.config_mut().app.windows { window.visible=false;window.focus=false;window.incognito=true; } }
    tauri::Builder::default().manage(Running::default()).manage(Arc::new(engine::Engine::default())).plugin(tauri_plugin_dialog::init()).plugin(tauri_plugin_opener::init())
      .setup(|app| { let warm_engine=app.state::<Arc<engine::Engine>>().inner().clone(); let warm_profile=std::env::var_os("RESEARCH_V3_PROFILE").map(PathBuf::from); let warm_legacy=if ui_review::enabled(){None}else{app.path().app_data_dir().ok()}; std::thread::spawn(move ||{let _=warm_engine.request(warm_profile,warm_legacy,serde_json::json!({"method":"runtime.info"}));}); if ui_review::enabled() { #[cfg(target_os="macos")] app.set_activation_policy(tauri::ActivationPolicy::Accessory); ui_review::arm_timeout(app.handle().clone()); } if std::env::var("RESEARCH_V3_DEBUG").as_deref()==Ok("1") { if let Some(window)=app.get_webview_window("main") { eprintln!("V3 URL: {:?}",window.url()); #[cfg(debug_assertions)] window.open_devtools(); } } Ok(()) })
      .on_page_load(|webview,payload| { if payload.event()==tauri::webview::PageLoadEvent::Finished { ui_review::install(webview); } })
      .invoke_handler(tauri::generate_handler![python_request,ui_review::review_fixture,ui_review::review_resize,ui_review::review_snapshot,ui_review::review_finish])
      .on_window_event(|window,event| { if let tauri::WindowEvent::CloseRequested{api,..}=event { if window.state::<Running>().0.load(Ordering::SeqCst)>0 { api.prevent_close();let _=window.emit("close-blocked",()); } } })
      .run(context).expect("启动科研数据工具集失败");
}
