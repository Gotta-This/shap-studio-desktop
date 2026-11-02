(async () => {
  const invoke = (cmd, args = {}) => window.__TAURI_INTERNALS__.invoke(cmd, args);
  const sleep = (ms) => ms <= 0 ? Promise.resolve() : new Promise(resolve => {
    const deadline=Date.now()+ms;
    const tick=()=>{if(Date.now()>=deadline){removeEventListener('__v3_review_tick',tick);resolve();}};
    addEventListener('__v3_review_tick',tick);
  });
  const steps = [], errors = [], timings = {};
  addEventListener('error', e => errors.push(e.message));
  addEventListener('unhandledrejection', e => errors.push(String(e.reason)));
  const wait = async (fn, label, ms = 60000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) { const value = fn(); if (value) return value; await sleep(120); }
    throw Error(label + ': ' + document.body.innerText.slice(-1000));
  };
  const button = (text) => [...document.querySelectorAll('button')].find(b => (b.innerText.trim() === text || b.getAttribute('aria-label') === text) && !b.disabled);
  const labelled = (text) => document.querySelector('[aria-label="' + text + '"]') || document.getElementById([...document.querySelectorAll('label')].find(l => l.innerText.replace(/\*/g,'').trim() === text)?.htmlFor || '');
  const click = async (node) => {
    await sleep(0); if (!node) throw Error('Missing control'); node.scrollIntoView({block:'center'});
    const rect=node.getBoundingClientRect();const options={bubbles:true,button:0,buttons:1,clientX:rect.x+rect.width/2,clientY:rect.y+rect.height/2};
    node.dispatchEvent(new PointerEvent('pointerdown',{...options,pointerType:'mouse'}));node.dispatchEvent(new MouseEvent('mousedown',options));
    node.focus?.({preventScroll:true});node.dispatchEvent(new PointerEvent('pointerup',{...options,buttons:0,pointerType:'mouse'}));node.dispatchEvent(new MouseEvent('mouseup',{...options,buttons:0}));node.click();await sleep(80);
  };
  const fill = (node, value) => { if (!node) throw Error('Missing input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value); node.dispatchEvent(new Event('input',{bubbles:true})); node.dispatchEvent(new Event('change',{bubbles:true})); };
  const tab = async (name) => click([...document.querySelectorAll('[role=tab]')].find(b => b.innerText.includes(name)));
  const route = async (path) => { location.hash = '#' + path; await sleep(250); };
  const snap = async (name) => { document.getElementById('app').scrollTop=0; await sleep(100); await invoke('review_snapshot',{name}); steps.push(name); };
  const upload = (input, name, data, type) => { if (!input) throw Error('Missing upload input'); const dt = new DataTransfer(); dt.items.add(new File([data],name,{type})); input.files=dt.files; input.dispatchEvent(new Event('change',{bubbles:true})); };
  const closeDialog = async () => { await click(document.querySelector('[data-slot=dialog-close]')); await sleep(80); };
  try {
    const style=document.createElement('style');style.textContent='*,*::before,*::after{animation:none!important;transition:none!important}';document.head.append(style);
    await wait(() => document.querySelector('h1')?.innerText.includes('丁丁宝宝'),'personal welcome');
    await wait(() => document.querySelector('img.brand-icon')?.naturalWidth > 0,'app icon');
    const state=await invoke('python_request',{request:{method:'state'}});
    if (!state.ok || !state.result.root.includes('data/workspace')) throw Error('Default workspace not connected');
    await wait(()=>document.querySelector('.weather-chip')?.innerText.includes('焦作') || document.querySelector('.weather-chip')?.innerText.includes('暂不可用'),'weather initialization',40000);
    await snap('01-home');
    const main=document.querySelector('.main-content');const before=main.getBoundingClientRect().width;
    await click(labelled('搜索任务与文件'));await wait(()=>document.querySelector('[role=dialog]'),'search dialog');
    if(Math.abs(main.getBoundingClientRect().width-before)>1)throw Error('Search changed the background width');
    await snap('02-search');await closeDialog();
    await click(labelled('收起侧栏'));await invoke('review_resize',{width:800});await sleep(200);
    if (Math.abs(document.querySelector('.sidebar').getBoundingClientRect().width-70)>1)throw Error('Narrow collapsed sidebar width');
    await snap('03-narrow-sidebar');await invoke('review_resize',{width:1440});await sleep(200);await click(labelled('展开侧栏'));
    await route('/settings');await wait(()=>button('检查更新'),'settings');
    if(button('迁移 Qt 数据'))throw Error('Qt migration is visible');
    await wait(()=>document.body.innerText.includes('应用数据目录'),'persistent data path');await snap('04-settings');
    await route('/workspace');await click(await wait(()=>button('新建任务'),'new task'));
    fill(labelled('客户 / 甲方'),'原生验收');fill(labelled('任务名称'),'原生界面验收任务');fill(document.querySelector('#first-todo'),'核对原生界面');
    await click(button('创建任务'));await wait(()=>document.querySelector('h1')?.innerText==='原生界面验收任务','created task');await snap('05-task');
    await click(button('导入材料'));await wait(()=>labelled('选择导入材料'),'material import');
    upload(labelled('选择导入材料'),'原生测试材料.txt',new TextEncoder().encode('原生 WebKit 材料预览测试'),'text/plain');
    await click(await wait(()=>[...document.querySelectorAll('button')].find(b=>b.innerText.includes('确认导入')&&!b.disabled),'confirm material import'));
    await wait(()=>document.body.innerText.includes('原生测试材料.txt'),'received material');await click(await wait(()=>button('预览'),'preview action'));
    await wait(()=>document.body.innerText.includes('原生 WebKit 材料预览测试'),'file preview');await snap('06-file-preview');await closeDialog();
    await route('/todos');await wait(()=>document.body.innerText.includes('核对原生界面'),'linked todo');await snap('07-todos');
    await route('/inbox');await wait(()=>document.querySelector('h1')?.innerText.includes('收件箱'),'inbox');await snap('08-inbox');
    await route('/tools/category');await click(await wait(()=>button('生成随机数列'),'category action'));
    await wait(()=>labelled('全部生成数值')?.value?.trim().split(/\n/).length===121,'category result');await snap('09-category');
    await route('/tools/numeric');const numericStarted=performance.now();await click(await wait(()=>button('生成模拟数据'),'numeric action'));
    await wait(()=>labelled('全部生成数值')?.value?.trim().split(/\n/).length===70,'numeric result');timings.numeric_ms=Math.round(performance.now()-numericStarted);await snap('10-numeric');
    await route('/tools/word');await wait(()=>labelled('导入 Word 文档'),'Word input');
    const bytes=await invoke('review_fixture');const wordStarted=performance.now();upload(labelled('导入 Word 文档'),'原生导入.docx',new Uint8Array(bytes),'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    const confirmGroups=await wait(()=>button('匹配并确认组别'),'Word scan and group confirmation');timings.word_scan_ms=Math.round(performance.now()-wordStarted);const applyStarted=performance.now();await click(confirmGroups);
    await wait(()=>document.body.innerText.includes('已确认组别'),'Word groups applied');timings.word_apply_ms=Math.round(performance.now()-applyStarted);await tab('表格匹配');await snap('11-word-import');
    await tab('生成与导出');await click(button('生成模拟数据'));await wait(()=>button('导出完整 Excel'),'Word generated Excel',90000);await snap('12-word-result');
    await route('/tools/shap');await wait(()=>labelled('样本量'),'SHAP default initialization');await snap('13-shap-parameters');
    await tab('模型与分类变量');await wait(()=>button('添加分类变量'),'SHAP model fields');await snap('14-shap-model');
    await tab('图表样式');await wait(()=>button('特征重要性条形图'),'SHAP style controls');await snap('15-shap-styles');
    await click(document.querySelector('[role=tab]'));
    const response=await invoke('python_request',{request:{method:'tool.shap.defaults'}});if(!response.ok)throw Error(response.error);
    const config=response.result;config.data.n_samples=80;config.plots.dpi=72;config.explanation.background_max_samples=10;
    for(const [key,value] of Object.entries(config.plots.plots))value.enabled=key==='bar';
    upload(document.querySelector('input[type=file]'),'native-analysis.json',JSON.stringify(config),'application/json');
    await wait(()=>labelled('样本量')?.value==='80','SHAP configuration restore');await click(button('生成完整分析'));
    await wait(()=>document.querySelector('img.result-figure')?.naturalWidth>0,'SHAP full analysis image',180000);await wait(()=>document.querySelector('[aria-label="结果图选择"]')?.textContent.trim() === document.querySelector('img.result-figure')?.alt, 'selected plot name is visible');await snap('16-shap-result');
    if(errors.length)throw Error(errors.join('\n'));
    await invoke('review_finish',{result:{ok:true,steps,errors,timings,mouse_moved:false,system_screen_recording:false,renderer:'actual app WKWebView',limitations:['OS file chooser/save dialogs and system application opening were not clicked; uploads used real in-memory files through the native webview.']}});
  } catch(e) {
    try { await invoke('review_snapshot',{name:'failure'}); } catch(_) {}
    await invoke('review_finish',{result:{ok:false,steps,errors,error:String(e),body:document.body.innerText.slice(-3000),inputs:[...document.querySelectorAll('input')].map(i=>({id:i.id,value:i.value,valid:i.validity.valid}))}});
  }
})();
