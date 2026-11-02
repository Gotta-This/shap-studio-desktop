//! Isolated app-owned UI verification. No system mouse, AX or screen recording.
use std::{path::PathBuf,sync::{OnceLock,atomic::{AtomicBool,Ordering}},time::Duration};
use tauri::Manager;
static FOLDER:OnceLock<PathBuf>=OnceLock::new();
static CLOSING:AtomicBool=AtomicBool::new(false);
static STARTED:AtomicBool=AtomicBool::new(false);
static FINISHED:AtomicBool=AtomicBool::new(false);
pub fn enabled()->bool { FOLDER.get().is_some() }
pub fn closing_test()->bool { CLOSING.load(Ordering::SeqCst) }
pub fn initialize(args:&[std::ffi::OsString]) {
    if args.get(1).is_some_and(|v|v=="--ui-review" || v=="--close-review") {
        CLOSING.store(args[1]=="--close-review",Ordering::SeqCst);
        let path=PathBuf::from(args.get(2).expect("UI review requires an isolated directory"));
        assert!(path.is_absolute(),"UI review directory must be absolute");
        std::fs::create_dir_all(&path).expect("UI review directory unavailable");
        std::env::set_var("RESEARCH_V3_DATA_ROOT",path.join("data"));
        std::env::remove_var("RESEARCH_V3_PROFILE");
        FOLDER.set(path).ok();
    }
}
pub fn install(webview:&tauri::Webview) {
    if enabled() && !STARTED.swap(true,Ordering::SeqCst) {
        let script=if closing_test() { r#"(async()=>{
            const invoke=(command,args={})=>window.__TAURI_INTERNALS__.invoke(command,args);
            await invoke('python_request',{request:{method:'todo.save',params:{text:'关闭验收：已保存的待办'}}});
            void invoke('python_request',{request:{method:'state'}}).catch(()=>{});
            await new Promise(resolve=>addEventListener('__v3_review_tick',resolve,{once:true}));
            await invoke('review_close');
        })().catch(error=>console.error(error));"# } else {include_str!("ui_review.js")};
        let _=webview.eval(script);
    }
}
pub fn arm_timeout(app:tauri::AppHandle) {
    if enabled() { std::thread::spawn(move||{
        let start=std::time::Instant::now();
        while !FINISHED.load(Ordering::SeqCst) && start.elapsed()<Duration::from_secs(480) {
            if let Some(window)=app.get_webview_window("main") { let _=window.eval("window.dispatchEvent(new Event('__v3_review_tick'))"); }
            std::thread::sleep(Duration::from_millis(100));
        }
        if !FINISHED.load(Ordering::SeqCst) { let _=std::fs::write(FOLDER.get().unwrap().join("native-ui-report.json"),r#"{"ok":false,"error":"Native UI review timed out"}"#);app.exit(1); }
    }); }
}
#[tauri::command]
pub fn review_fixture()->Result<Vec<u8>,String>{std::fs::read(FOLDER.get().ok_or("Not in UI review mode")?.join("fixture.docx")).map_err(|e|e.to_string())}
#[tauri::command]
pub fn review_resize(app:tauri::AppHandle,width:f64)->Result<(),String>{
    if !enabled(){return Err("Not in UI review mode".into());}
    app.get_webview_window("main").ok_or("Window unavailable")?.set_size(tauri::LogicalSize::new(width.clamp(800.,1600.),960.)).map_err(|e|e.to_string())
}
#[tauri::command]
pub fn review_finish(app:tauri::AppHandle,result:serde_json::Value)->Result<(),String>{
    let folder=FOLDER.get().ok_or("Not in UI review mode")?;
    std::fs::write(folder.join("native-ui-report.json"),serde_json::to_vec_pretty(&result).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
    FINISHED.store(true,Ordering::SeqCst);app.exit(if result.get("ok").and_then(|v|v.as_bool())==Some(true){0}else{1});Ok(())
}
#[tauri::command]
pub async fn review_snapshot(app:tauri::AppHandle,name:String)->Result<String,String>{
    let folder=FOLDER.get().ok_or("Not in UI review mode")?;
    if name.is_empty() || !name.chars().all(|c|c.is_ascii_alphanumeric()||c=='-'){return Err("Invalid screenshot name".into());}
    let path=folder.join(format!("{name}.png"));
    #[cfg(target_os="macos")]
    {
        use objc2::{msg_send,class,runtime::AnyObject};
        let (tx,rx)=std::sync::mpsc::channel();let target=path.clone();
        app.get_webview_window("main").ok_or("Window unavailable")?.with_webview(move|webview|{
            let callback=block2::RcBlock::new(move|image:*mut AnyObject,_error:*mut AnyObject|{
                let result=(||->Result<(),String>{
                    if image.is_null(){return Err("WKWebView snapshot returned no image".into());}
                    // WKWebView supplies the image on its UI thread; NSData stays alive through this callback.
                    unsafe {
                        let tiff:*mut AnyObject=msg_send![image,TIFFRepresentation];
                        let bitmap:*mut AnyObject=msg_send![class!(NSBitmapImageRep),imageRepWithData:tiff];
                        let properties:*mut AnyObject=msg_send![class!(NSDictionary),dictionary];
                        let png:*mut AnyObject=msg_send![bitmap,representationUsingType:4usize,properties:properties];
                        if png.is_null(){return Err("PNG encoding failed".into());}
                        let bytes:*const std::ffi::c_void=msg_send![png,bytes];let size:usize=msg_send![png,length];
                        std::fs::write(&target,std::slice::from_raw_parts(bytes.cast::<u8>(),size)).map_err(|e|e.to_string())?;
                    } Ok(())
                })();let _=tx.send(result);
            });
            unsafe {let view=webview.inner() as *mut AnyObject;let _:()=msg_send![view,takeSnapshotWithConfiguration:std::ptr::null::<AnyObject>(),completionHandler:&*callback];}
        }).map_err(|e|e.to_string())?;
        tauri::async_runtime::spawn_blocking(move||rx.recv_timeout(Duration::from_secs(30))).await.map_err(|e|e.to_string())?.map_err(|e|e.to_string())??;
        return Ok(path.to_string_lossy().into_owned());
    }
    #[cfg(not(target_os="macos"))]
    {let _=(app,path);Err("App-owned snapshots are currently available on macOS".into())}
}

#[tauri::command]
pub fn review_close(app:tauri::AppHandle)->Result<(),String> {
    if !closing_test(){return Err("Not in close review mode".into());}
    let active=app.state::<crate::Running>().0.load(Ordering::SeqCst);
    if active==0{return Err("Close verification requires an active request".into());}
    let requested_at_ms=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e|e.to_string())?.as_millis();
    std::fs::write(FOLDER.get().unwrap().join("close-request.json"),serde_json::json!({"active_requests":active,"requested_at_ms":requested_at_ms}).to_string()).map_err(|e|e.to_string())?;
    app.get_webview_window("main").ok_or("Window unavailable")?.close().map_err(|e|e.to_string())
}
pub fn record_close(window:&tauri::Window) {
    if closing_test() {
        let value=serde_json::json!({"native_close_event":true,"active_requests":window.state::<crate::Running>().0.load(Ordering::SeqCst),"mouse_moved":false});
        let _=std::fs::write(FOLDER.get().unwrap().join("native-close-report.json"),value.to_string());
        FINISHED.store(true,Ordering::SeqCst);
    }
}
