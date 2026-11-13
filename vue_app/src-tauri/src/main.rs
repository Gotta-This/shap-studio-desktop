#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{Read, Write}, path::PathBuf, process::{Command,Stdio}, sync::{Arc,atomic::{AtomicUsize,Ordering}}};
use tauri::{Emitter,Manager};
mod ui_review;
mod engine;
#[derive(Clone,Default)]
struct Running(Arc<AtomicUsize>);
struct CountGuard(Arc<AtomicUsize>);
impl Drop for CountGuard { fn drop(&mut self) { self.0.fetch_sub(1,Ordering::SeqCst); } }

#[cfg(target_os="macos")]
fn quickshot_region_hotkey() -> (u16,u64) {
    let default="Cmd+Shift+A".to_string();
    let home=std::env::var_os("HOME").map(PathBuf::from);
    let config=home.map(|h|h.join(".config").join("QuickShot").join("config.toml"));
    let value=config.and_then(|p|std::fs::read_to_string(p).ok()).and_then(|text|text.lines().find_map(|line| {
        let line=line.trim();
        if !line.starts_with("region") { return None; }
        line.split_once('=')?.1.trim().trim_matches('"').split('#').next().map(|v|v.trim().to_string())
    })).unwrap_or(default);
    let mut flags=0u64;
    let mut key=None;
    for token in value.split('+').map(str::trim).filter(|v|!v.is_empty()) {
        match token.to_ascii_lowercase().as_str() {
            "cmd"|"command"|"meta" => flags|=1<<20,
            "ctrl"|"control" => flags|=1<<18,
            "alt"|"opt"|"option" => flags|=1<<19,
            "shift" => flags|=1<<17,
            _ => key=Some(token.to_string()),
        }
    }
    let key=key.unwrap_or_else(||"A".to_string()).to_ascii_uppercase();
    let code=match key.as_str() {
        "A"=>0,"B"=>11,"C"=>8,"D"=>2,"E"=>14,"F"=>3,"G"=>5,"H"=>4,"I"=>34,"J"=>38,"K"=>40,"L"=>37,"M"=>46,"N"=>45,"O"=>31,"P"=>35,"Q"=>12,"R"=>15,"S"=>1,"T"=>17,"U"=>32,"V"=>9,"W"=>13,"X"=>7,"Y"=>16,"Z"=>6,
        "0"=>29,"1"=>18,"2"=>19,"3"=>20,"4"=>21,"5"=>23,"6"=>22,"7"=>26,"8"=>28,"9"=>25,
        "F1"=>122,"F2"=>120,"F3"=>99,"F4"=>118,"F5"=>96,"F6"=>97,"F7"=>98,"F8"=>100,"F9"=>101,"F10"=>109,"F11"=>103,"F12"=>111,"F13"=>105,"F14"=>107,"F15"=>113,"F16"=>106,"F17"=>64,"F18"=>79,"F19"=>80,"F20"=>90,
        _=>0,
    };
    (code,flags)
}

#[cfg(target_os="macos")]
fn post_quickshot_region_hotkey() -> Result<(),String> {
    use std::ffi::c_void;
    #[link(name="CoreGraphics",kind="framework")]
    extern "C" {
        fn CGEventSourceCreate(state:u32)->*mut c_void;
        fn CGEventCreateKeyboardEvent(source:*const c_void,keycode:u16,keydown:bool)->*mut c_void;
        fn CGEventSetFlags(event:*mut c_void,flags:u64);
        fn CGEventPost(tap:u32,event:*mut c_void);
        fn CFRelease(value:*const c_void);
    }
    let (keycode,flags)=quickshot_region_hotkey();
    unsafe {
        let source=CGEventSourceCreate(0);
        if source.is_null() { return Err("macOS 无法创建键盘事件源，请检查辅助功能权限。".into()); }
        for down in [true,false] {
            let event=CGEventCreateKeyboardEvent(source,keycode,down);
            if event.is_null() { CFRelease(source); return Err("macOS 无法创建截图快捷键事件，请检查辅助功能权限。".into()); }
            CGEventSetFlags(event,flags);
            CGEventPost(0,event);
            CFRelease(event);
        }
        CFRelease(source);
    }
    Ok(())
}

#[cfg(target_os="windows")]
fn post_quickshot_region_hotkey() -> Result<(),String> {
    use std::mem::size_of;
    #[repr(C)] #[derive(Clone,Copy)] struct KeyboardInput { vk:u16, scan:u16, flags:u32, time:u32, extra:usize }
    #[repr(C)] #[derive(Clone,Copy)] struct MouseInput { dx:i32, dy:i32, mouse_data:u32, flags:u32, time:u32, extra:usize }
    #[repr(C)] #[derive(Clone,Copy)] union InputUnion { keyboard:KeyboardInput, mouse:MouseInput }
    #[repr(C)] #[derive(Clone,Copy)] struct Input { input_type:u32, data:InputUnion }
    #[link(name="user32")]
    unsafe extern "system" { fn SendInput(count:u32,inputs:*const Input,size:i32)->u32; }
    const KEYUP:u32=0x0002;
    let key=|vk:u16,flags:u32|Input{input_type:1,data:InputUnion{keyboard:KeyboardInput{vk,scan:0,flags,time:0,extra:0}}};
    let events=[key(0x11,0),key(0x10,0),key(0x41,0),key(0x41,KEYUP),key(0x10,KEYUP),key(0x11,KEYUP)];
    let sent=unsafe{SendInput(events.len() as u32,events.as_ptr(),size_of::<Input>() as i32)};
    if sent==events.len() as u32 { Ok(()) } else { Err("Windows 无法发送 QuickShot 快捷键，请检查辅助功能权限。".into()) }
}

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
        let result=engine.request(profile,legacy,request);
        // Isolated close verification emulates a slow IPC response.
        if ui_review::closing_test() { std::thread::sleep(std::time::Duration::from_secs(3)); }
        result
    }).await.map_err(|e|e.to_string())?
}
#[tauri::command]
fn quickshot_capture(app:tauri::AppHandle) -> Result<(),String> {
    let name=if cfg!(windows){"quickshot.exe"}else{"quickshot"};
    let current=std::env::current_exe().map_err(|e|e.to_string())?;
    let resource=app.path().resource_dir().map_err(|e|e.to_string())?;
    let source_name=if cfg!(windows) { "quickshot-x86_64-pc-windows-msvc.exe" } else if cfg!(target_arch="aarch64") { "quickshot-aarch64-apple-darwin" } else { "quickshot-x86_64-apple-darwin" };
    let source=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries").join(source_name);
    let candidates=vec![current.parent().map(|p|p.join(name)),Some(resource.join(name)),Some(source)];
    let executable=candidates.iter().flatten().find(|p|p.is_file()).cloned().ok_or_else(||format!("QuickShot 组件未找到，已检查：{}",candidates.iter().flatten().map(|p|p.display().to_string()).collect::<Vec<_>>().join("、")))?;
    #[cfg(target_os="macos")]
    {
        let app_bundle=resource.join("resources").join("quickshot").join("QuickShot.app");
        let app_executable=app_bundle.join("Contents").join("MacOS").join("QuickShot");
        if app_executable.is_file() {
            if !quickshot_running(&app_executable) {
                launch_quickshot(&app_bundle)?;
                std::thread::sleep(std::time::Duration::from_millis(700));
            }
            return post_quickshot_region_hotkey();
        }
    }
    let mut command=Command::new(executable);
    command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)] { use std::os::windows::process::CommandExt;command.creation_flags(0x08000000); }
    command.spawn().map_err(|e|format!("无法启动 QuickShot：{e}"))?;
    #[cfg(target_os="macos")]
    { std::thread::sleep(std::time::Duration::from_millis(700)); return post_quickshot_region_hotkey(); }
    #[cfg(target_os="windows")]
    { std::thread::sleep(std::time::Duration::from_millis(250)); return post_quickshot_region_hotkey(); }
    #[cfg(not(any(target_os="macos",target_os="windows")))]
    Ok(())
}
#[cfg(target_os="macos")]
fn quickshot_running(executable:&PathBuf) -> bool {
    Command::new("pgrep").args(["-fx",executable.to_string_lossy().as_ref()]).status().is_ok_and(|status|status.success())
}
#[cfg(target_os="macos")]
fn launch_quickshot(bundle:&PathBuf) -> Result<(),String> {
    Command::new("open").args(["-g",bundle.to_string_lossy().as_ref()]).spawn().map(|_|()).map_err(|e|format!("无法启动 QuickShot：{e}"))
}
fn quickshot_config_path() -> Result<PathBuf,String> {
    #[cfg(target_os="windows")]
    { let appdata=std::env::var_os("APPDATA").map(PathBuf::from).ok_or("无法确定用户配置目录")?; return Ok(appdata.join("QuickShot").join("config.toml")); }
    #[cfg(not(target_os="windows"))]
    { let home=std::env::var_os("HOME").map(PathBuf::from).ok_or("无法确定用户目录")?; return Ok(home.join(".config").join("QuickShot").join("config.toml")); }
}
fn quickshot_default_config() -> String {
    let region=if cfg!(target_os="windows") { "Ctrl+Shift+A" } else { "Cmd+Shift+A" };
    let fullscreen=if cfg!(target_os="windows") { "Ctrl+Shift+S" } else { "Cmd+Shift+S" };
    let directory=if cfg!(target_os="windows") { "~/Pictures" } else { "~/Desktop" };
    format!("# QuickShot settings — edits are reloaded automatically.\n\n[hotkey]\nregion = \"{region}\"\nfullscreen = \"{fullscreen}\"\n\n[save]\nenabled = false\ndirectory = \"{directory}\"\nfilename_template = \"Screenshot_{{datetime}}.png\"\n\n[general]\nnotification_on_fullscreen = true\n")
}
fn ensure_quickshot_config() -> Result<PathBuf,String> {
    let path=quickshot_config_path()?;
    if let Some(parent)=path.parent() { std::fs::create_dir_all(parent).map_err(|e|e.to_string())?; }
    if !path.exists() { std::fs::write(&path,quickshot_default_config()).map_err(|e|e.to_string())?; }
    Ok(path)
}
fn quickshot_config_value(text:&str, key:&str, default:&str) -> String {
    text.lines().find_map(|line| {
        let trimmed=line.trim();
        if !trimmed.starts_with(key) || !trimmed[key.len()..].trim_start().starts_with('=') { return None; }
        let value=trimmed.split_once('=')?.1.split('#').next()?.trim().trim_matches('"').trim();
        (!value.is_empty()).then(||value.to_string())
    }).unwrap_or_else(||default.to_string())
}
fn valid_quickshot_shortcut(value:&str) -> bool {
    let parts:Vec<_>=value.split('+').map(str::trim).filter(|part|!part.is_empty()).collect();
    if parts.is_empty() { return false; }
    let key=parts[parts.len()-1];
    let modifier=|part:&str| matches!(part.to_ascii_lowercase().as_str(),"cmd"|"command"|"ctrl"|"control"|"alt"|"opt"|"option"|"shift"|"meta"|"super");
    if parts[..parts.len()-1].iter().any(|part|!modifier(part)) { return false; }
    let upper=key.to_ascii_uppercase();
    (upper.len()==1 && upper.chars().next().is_some_and(|c|c.is_ascii_alphanumeric()))
      || (upper.strip_prefix('F').and_then(|n|n.parse::<u8>().ok()).is_some_and(|n|(1..=24).contains(&n)))
      || matches!(upper.as_str(),"SPACE"|"ENTER"|"TAB"|"BACKSPACE"|"ESCAPE")
}
#[tauri::command]
fn quickshot_config() -> Result<serde_json::Value,String> {
    let path=ensure_quickshot_config()?;
    let text=std::fs::read_to_string(path).map_err(|e|e.to_string())?;
    Ok(serde_json::json!({"region":quickshot_config_value(&text,"region",if cfg!(target_os="windows"){"Ctrl+Shift+A"}else{"Cmd+Shift+A"}),"fullscreen":quickshot_config_value(&text,"fullscreen",if cfg!(target_os="windows"){"Ctrl+Shift+S"}else{"Cmd+Shift+S"})}))
}
#[tauri::command]
fn set_quickshot_config(region:String, fullscreen:String) -> Result<serde_json::Value,String> {
    if !valid_quickshot_shortcut(&region) || !valid_quickshot_shortcut(&fullscreen) { return Err("快捷键格式无效，请使用 Cmd+Shift+A 或 Ctrl+Alt+R 这样的格式。".into()); }
    let path=ensure_quickshot_config()?;
    let original=std::fs::read_to_string(&path).map_err(|e|e.to_string())?;
    let mut found_region=false; let mut found_fullscreen=false; let mut lines=Vec::new();
    for line in original.lines() {
        let trimmed=line.trim_start();
        if trimmed.starts_with("region") && trimmed["region".len()..].trim_start().starts_with('=') { lines.push(format!("region = \"{region}\"")); found_region=true; }
        else if trimmed.starts_with("fullscreen") && trimmed["fullscreen".len()..].trim_start().starts_with('=') { lines.push(format!("fullscreen = \"{fullscreen}\"")); found_fullscreen=true; }
        else { lines.push(line.to_string()); }
    }
    if !found_region { lines.push("[hotkey]".into()); lines.push(format!("region = \"{region}\"")); }
    if !found_fullscreen { lines.push(format!("fullscreen = \"{fullscreen}\"")); }
    let temp=path.with_extension("toml.tmp");
    std::fs::write(&temp,format!("{}\n",lines.join("\n"))).map_err(|e|e.to_string())?;
    std::fs::rename(&temp,&path).map_err(|e|e.to_string())?;
    Ok(serde_json::json!({"region":region,"fullscreen":fullscreen}))
}
#[tauri::command]
fn quickshot_open_config() -> Result<(),String> {
    let path=ensure_quickshot_config()?;
    #[cfg(target_os="windows")]
    { Command::new("cmd").args(["/C","start","",path.to_string_lossy().as_ref()]).spawn().map(|_|()).map_err(|e|format!("无法打开 QuickShot 配置：{e}")) }
    #[cfg(not(target_os="windows"))]
    { Command::new("open").arg(path).spawn().map(|_|()).map_err(|e|format!("无法打开 QuickShot 配置：{e}")) }
}
fn todo_island_preference(app:&tauri::AppHandle) -> Result<PathBuf,String> {
    Ok(app.path().app_data_dir().map_err(|e|e.to_string())?.join("todo-island-enabled"))
}
fn todo_island_config_path(app:&tauri::AppHandle) -> Result<PathBuf,String> {
    Ok(app.path().app_data_dir().map_err(|e|e.to_string())?.join("todo-island-config.json"))
}
fn todo_island_config(app:&tauri::AppHandle) -> Result<serde_json::Value,String> {
    let path=todo_island_config_path(app)?;
    let defaults=serde_json::json!({"compact_width":240,"expanded_width":380,"show_screenshot":true});
    let Some(parent)=path.parent() else { return Ok(defaults); };
    std::fs::create_dir_all(parent).map_err(|e|e.to_string())?;
    if !path.exists() { std::fs::write(&path,serde_json::to_vec_pretty(&defaults).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?; return Ok(defaults); }
    let value=std::fs::read_to_string(&path).ok().and_then(|text|serde_json::from_str::<serde_json::Value>(&text).ok()).unwrap_or(defaults.clone());
    let compact=value.get("compact_width").and_then(|v|v.as_u64()).unwrap_or(240).clamp(180,800);
    let expanded=value.get("expanded_width").and_then(|v|v.as_u64()).unwrap_or(380).clamp(280,1000).max(compact);
    let show_screenshot=value.get("show_screenshot").and_then(|v|v.as_bool()).unwrap_or(true);
    Ok(serde_json::json!({"compact_width":compact,"expanded_width":expanded,"show_screenshot":show_screenshot}))
}
fn todo_island_widths(app:&tauri::AppHandle) -> (f64,f64) {
    todo_island_config(app).ok().map(|v|(
        v["compact_width"].as_u64().unwrap_or(240) as f64,
        v["expanded_width"].as_u64().unwrap_or(380) as f64,
    )).unwrap_or((240.,380.))
}
fn todo_island_enabled_inner(app:&tauri::AppHandle) -> bool {
    todo_island_preference(app).ok().and_then(|p|std::fs::read_to_string(p).ok()).is_some_and(|v|v.trim()=="true")
}
fn open_todo_island(app:&tauri::AppHandle) -> Result<(),String> {
    if app.get_webview_window("todo-island").is_some() { return Ok(()); }
    let (compact_width,_)=todo_island_widths(app);
    let mut builder=tauri::WebviewWindowBuilder::new(app,"todo-island",tauri::WebviewUrl::App("index.html#/todo-island".into()))
        .title("待办灵动岛")
        .inner_size(compact_width,44.)
        .min_inner_size(180.,40.)
        .decorations(false)
        .always_on_top(true)
        .resizable(false)
        .transparent(true)
        .shadow(false)
        .focusable(true)
        .accept_first_mouse(true)
        .skip_taskbar(true);
    if let Some(monitor)=app.get_webview_window("main").and_then(|w|w.current_monitor().ok().flatten()) {
        let scale=monitor.scale_factor();
        let x=monitor.position().x as f64/scale+(monitor.size().width as f64/scale-compact_width)/2.;
        let y=monitor.position().y as f64/scale+8.;
        builder=builder.position(x,y);
    } else { builder=builder.center(); }
    builder.build().map(|_|()).map_err(|e|format!("无法打开待办灵动岛：{e}"))
}
#[cfg(target_os="macos")]
fn start_todo_island_mouse_monitor(app:tauri::AppHandle) {
    use std::{ffi::c_void,thread,time::Duration};
    #[repr(C)] struct CGPoint { x:f64, y:f64 }
    #[link(name="CoreGraphics",kind="framework")]
    extern "C" {
        fn CGEventCreate(source:*const c_void)->*mut c_void;
        fn CGEventGetLocation(event:*const c_void)->CGPoint;
        fn CFRelease(value:*const c_void);
    }
    thread::spawn(move || {
        let mut inside=false;
        loop {
            let next=app.get_webview_window("todo-island").and_then(|window| {
                if !window.is_visible().ok().unwrap_or(false) { return Some(false); }
                let position=window.outer_position().ok()?;
                let size=window.outer_size().ok()?;
                let scale=window.scale_factor().ok().filter(|value|*value>0.).unwrap_or(1.);
                let event=unsafe { CGEventCreate(std::ptr::null()) };
                if event.is_null() { return Some(false); }
                let point=unsafe { CGEventGetLocation(event) };
                unsafe { CFRelease(event); }
                let left=position.x as f64/scale;
                let top=position.y as f64/scale;
                let right=left+size.width as f64/scale;
                let bottom=top+size.height as f64/scale;
                Some(point.x>=left && point.x<=right && point.y>=top && point.y<=bottom)
            }).unwrap_or(false);
            if next!=inside {
                inside=next;
                let _=app.emit("todo-island-hover",inside);
            }
            thread::sleep(Duration::from_millis(40));
        }
    });
}
#[tauri::command]
fn todo_island_enabled(app:tauri::AppHandle) -> bool { todo_island_enabled_inner(&app) }
#[tauri::command]
fn todo_island_config_command(app:tauri::AppHandle) -> Result<serde_json::Value,String> { todo_island_config(&app) }
#[tauri::command]
fn set_todo_island_config(app:tauri::AppHandle, config:serde_json::Value) -> Result<serde_json::Value,String> {
    let compact=config.get("compact_width").and_then(|v|v.as_u64()).ok_or("收起宽度必须是整数")?.clamp(180,800);
    let expanded=config.get("expanded_width").and_then(|v|v.as_u64()).ok_or("展开宽度必须是整数")?.clamp(280,1000);
    if expanded < compact { return Err("展开宽度不能小于收起宽度".into()); }
    let current=todo_island_config(&app)?;
    let show_screenshot=config.get("show_screenshot").and_then(|v|v.as_bool()).or_else(||current.get("show_screenshot").and_then(|v|v.as_bool())).unwrap_or(true);
    let value=serde_json::json!({"compact_width":compact,"expanded_width":expanded,"show_screenshot":show_screenshot});
    let path=todo_island_config_path(&app)?;
    if let Some(parent)=path.parent() { std::fs::create_dir_all(parent).map_err(|e|e.to_string())?; }
    let temp=path.with_extension("json.tmp");
    std::fs::write(&temp,serde_json::to_vec_pretty(&value).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
    std::fs::rename(&temp,&path).map_err(|e|e.to_string())?;
    let _=app.emit("todo-island-config-updated",value.clone());
    Ok(value)
}
#[tauri::command]
fn set_todo_island_enabled(app:tauri::AppHandle, enabled:bool) -> Result<(),String> {
    if enabled { open_todo_island(&app)?; }
    else if let Some(window)=app.get_webview_window("todo-island") { window.close().map_err(|e|format!("无法关闭待办灵动岛：{e}"))?; }
    let path=todo_island_preference(&app)?;
    if let Some(parent)=path.parent() { std::fs::create_dir_all(parent).map_err(|e|e.to_string())?; }
    std::fs::write(path,if enabled {"true"} else {"false"}).map_err(|e|e.to_string())
}
fn start_quickshot_daemon(app:&tauri::AppHandle) -> Result<(),String> {
    let name=if cfg!(windows){"quickshot.exe"}else{"quickshot"};
    let current=std::env::current_exe().map_err(|e|e.to_string())?;
    let resource=app.path().resource_dir().map_err(|e|e.to_string())?;
    #[cfg(target_os="macos")]
    {
        let app_bundle=resource.join("resources").join("quickshot").join("QuickShot.app");
        let app_executable=app_bundle.join("Contents").join("MacOS").join("QuickShot");
        if app_executable.is_file() {
            if !quickshot_running(&app_executable) { launch_quickshot(&app_bundle)?; }
            return Ok(());
        }
    }
    let source_name=if cfg!(windows) { "quickshot-x86_64-pc-windows-msvc.exe" } else if cfg!(target_arch="aarch64") { "quickshot-aarch64-apple-darwin" } else { "quickshot-x86_64-apple-darwin" };
    let source=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries").join(source_name);
    let candidates=vec![current.parent().map(|p|p.join(name)),Some(resource.join(name)),Some(source)];
    let executable=candidates.iter().flatten().find(|p|p.is_file()).cloned().ok_or_else(||format!("QuickShot 组件未找到，已检查：{}",candidates.iter().flatten().map(|p|p.display().to_string()).collect::<Vec<_>>().join("、")))?;
    let mut command=Command::new(executable);
    command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)] { use std::os::windows::process::CommandExt;command.creation_flags(0x08000000); }
    command.spawn().map(|_|()).map_err(|e|format!("无法启动 QuickShot：{e}"))
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
      .setup(|app| { let warm_engine=app.state::<Arc<engine::Engine>>().inner().clone(); let warm_profile=std::env::var_os("RESEARCH_V3_PROFILE").map(PathBuf::from); let warm_legacy=if ui_review::enabled(){None}else{app.path().app_data_dir().ok()}; std::thread::spawn(move ||{let _=warm_engine.request(warm_profile,warm_legacy,serde_json::json!({"method":"runtime.info"}));}); if !ui_review::enabled() { let _=start_quickshot_daemon(app.handle()); if todo_island_enabled_inner(app.handle()) { let _=open_todo_island(app.handle()); } #[cfg(target_os="macos")] start_todo_island_mouse_monitor(app.handle().clone()); } if ui_review::enabled() { #[cfg(target_os="macos")] app.set_activation_policy(tauri::ActivationPolicy::Accessory); ui_review::arm_timeout(app.handle().clone()); } if std::env::var("RESEARCH_V3_DEBUG").as_deref()==Ok("1") { if let Some(window)=app.get_webview_window("main") { eprintln!("V3 URL: {:?}",window.url()); #[cfg(debug_assertions)] window.open_devtools(); } } Ok(()) })
      .plugin(tauri_plugin_global_shortcut::Builder::new().build())
      .on_page_load(|webview,payload| { if payload.event()==tauri::webview::PageLoadEvent::Finished { ui_review::install(webview); } })
      .invoke_handler(tauri::generate_handler![python_request,quickshot_capture,quickshot_config,set_quickshot_config,quickshot_open_config,todo_island_enabled,todo_island_config_command,set_todo_island_config,set_todo_island_enabled,ui_review::review_fixture,ui_review::review_resize,ui_review::review_snapshot,ui_review::review_finish,ui_review::review_close])
      .on_window_event(|window,event| {
          if let tauri::WindowEvent::CloseRequested{..}=event {
              ui_review::record_close(window);
              if window.label() == "main" { window.app_handle().exit(0); }
          }
      })
      .run(context).expect("启动科研数据工具集失败");
}
