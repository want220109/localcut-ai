const {app,BrowserWindow,ipcMain,dialog,protocol,net,shell} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const {pathToFileURL} = require('node:url');
const {projectId,inside,validMedia,trustedSender} = require('./policy.cjs');
const {UpdateController} = require('../../updater/controller.cjs');
const updateConfig = require('../../updater/config.json');
protocol.registerSchemesAsPrivileged([{scheme:'local-media',privileges:{standard:true,secure:true,stream:true,supportFetchAPI:true}}]);
app.setName('LocalCut AI');
let window, busy=false, updateController;
const grants=new Map();
const dataRoot=path.join(app.getPath('userData'),'workspace');
const projectRoot=path.resolve(__dirname,'../..');
const rendererFile=path.join(__dirname,'../renderer/index.html');
const devUrl=!app.isPackaged && process.env.LOCALCUT_DEV_URL==='http://127.0.0.1:5173' ? process.env.LOCALCUT_DEV_URL : null;
function mediaUrl(filename) {
  const token=crypto.randomBytes(24).toString('hex');grants.set(token,filename);
  return 'local-media://asset/'+token;
}
function decorate(result) {
  const p=result.project||result;
  if(p.source) {
    const preview=p.preview && inside(path.join(dataRoot,'jobs',projectId(p.id)),path.resolve(p.preview)) ? p.preview : p.source.path;
    p.sourceUrl=mediaUrl(preview);
    if(p.output?.path && inside(path.join(dataRoot,'jobs',projectId(p.id)),path.resolve(p.output.path))) p.outputUrl=mediaUrl(p.output.path);
  }
  return result;
}
async function engine(request,lock=true) {
  if(lock && busy) throw new Error('진행 중인 작업이 있습니다. 완료 후 다시 시도해 주세요.');
  if(lock) busy=true;
  try {
    const python=process.env.LOCALCUT_PYTHON || path.join(projectRoot,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    const executable=app.isPackaged ? path.join(process.resourcesPath,'engine','localcut-engine.exe') : python;
    const args=app.isPackaged ? [] : ['-m','engine.service'];
    return await new Promise((resolve,reject)=>{
      const child=spawn(executable,args,{cwd:app.isPackaged?process.resourcesPath:projectRoot,windowsHide:true,
        env:{...process.env,PYTHONIOENCODING:'utf-8',...(app.isPackaged?{LOCALCUT_MEDIA_DIR:path.join(process.resourcesPath,'media')}:{})},
        stdio:['pipe','pipe','pipe']});
      let buffer='',stderr='',result,error;
      child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
      child.stderr.on('data',s=>{stderr=(stderr+s).slice(-5000);});
      child.stdout.on('data',chunk=>{
        buffer+=chunk;
        if(buffer.length>60*1024*1024){error='엔진 응답이 너무 큽니다.';child.kill();return;}
        let boundary;
        while((boundary=buffer.indexOf('\n'))>=0) {
          const line=buffer.slice(0,boundary);buffer=buffer.slice(boundary+1);
          try {
            const event=JSON.parse(line);
            if(event.type==='progress') window?.webContents.send('progress',event);
            if(event.type==='result') result=event.data;
            if(event.type==='error') error=event.message;
          } catch {error='엔진 응답을 읽을 수 없습니다.';}
        }
      });
      child.on('error',reject);
      child.on('close',code=>{if(error || code!==0 || result===undefined) reject(new Error(error||stderr||'영상 엔진이 예기치 않게 종료되었습니다.'));else resolve(result);});
      child.stdin.on('error',()=>{});
      child.stdin.end(JSON.stringify({root:dataRoot,...request})+'\n');
    });
  } finally {if(lock) busy=false;}
}
async function importVideo(filename) {
  if(!validMedia(filename)) throw new Error('MP4, MOV, AVI, MKV 영상만 불러올 수 있습니다.');
  return decorate(await engine({action:'create',source:await fs.realpath(filename)}));
}
async function request(event,message) {
  if(event.sender!==window?.webContents || !trustedSender(event.senderFrame?.url||'',rendererFile,devUrl)) throw new Error('허용하지 않는 요청입니다.');
  if(!message || typeof message.action!=='string') throw new Error('잘못된 요청입니다.');
  const {action}=message;
  if(action==='health') return engine({action:'health'},false);
  if(action==='history') return engine({action:'list'},false);
  if(action==='pick') {
    if(busy) throw new Error('현재 작업을 마친 후 영상을 불러와 주세요.');
    const r=await dialog.showOpenDialog(window,{properties:['openFile'],filters:[{name:'영상',extensions:['mp4','mov','avi','mkv']}]});
    return r.canceled?null:importVideo(r.filePaths[0]);
  }
  if(action==='import') return importVideo(message.path);
  if(action==='model') {
    if(!['tiny','small'].includes(message.model)) throw new Error('지원하지 않는 모델입니다.');
    let importDir;
    if(message.import) {
      const r=await dialog.showOpenDialog(window,{title:'faster-whisper 모델 폴더 선택',properties:['openDirectory']});
      if(r.canceled) return null;
      importDir=r.filePaths[0];
    } else if(message.consent!==true) throw new Error('모델 다운로드 동의가 필요합니다.');
    return engine({action:'install_model',model:message.model,importDir});
  }
  if(action==='updateStatus') return updateController.state;
  if(action==='update') return updateController.action(message.operation,message.channel);
  const id=projectId(message.id);
  if(['get','analyze','render','undo','edit','command'].includes(action)) {
    const allowed={action,id};
    if(action==='edit') allowed.changes=message.changes;
    if(action==='command') allowed.text=message.text;
    if(action==='analyze') allowed.model=message.model;
    return decorate(await engine(allowed,action!=='get'));
  }
  if(action==='export' || action==='reveal') {
    if(busy) throw new Error('영상 처리 완료 후 저장해 주세요.');
    const {project:p}=await engine({action:'get',id});
    if(!p.output) throw new Error('먼저 MP4를 출력해 주세요.');
    const filename=p.output[message.kind==='srt'?'srt':message.kind==='report'?'report':'path'];
    const real=await fs.realpath(filename);
    if(!inside(await fs.realpath(path.join(dataRoot,'jobs',id)),real)) throw new Error('작업 폴더 밖의 파일을 내보낼 수 없습니다.');
    if(action==='reveal') {shell.showItemInFolder(real);return true;}
    const extension=path.extname(real).slice(1);
    const r=await dialog.showSaveDialog(window,{defaultPath:p.name+(extension==='mp4'?'-편집':'')+'.'+extension,filters:[{name:extension.toUpperCase(),extensions:[extension]}]});
    if(r.canceled) return null;
    const target=path.resolve(r.filePath);
    // Protect the original even if a user selects it in the Save dialog (including hard links).
    const sourceStat=await fs.stat(p.source.path);
    let targetStat;try {targetStat=await fs.stat(target);}catch(err){if(err.code!=='ENOENT')throw err;}
    if(target===path.resolve(p.source.path) || (targetStat && targetStat.dev===sourceStat.dev && targetStat.ino===sourceStat.ino)) throw new Error('원본 영상에는 저장할 수 없습니다. 다른 이름을 선택해 주세요.');
    if(target===real) return target;
    await fs.copyFile(real,target);
    return target;
  }
  throw new Error('지원하지 않는 요청입니다.');
}
if(!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance',()=>{window?.show();window?.focus();});
  app.whenReady().then(async()=>{
    await fs.mkdir(dataRoot,{recursive:true});
    protocol.handle('local-media',async req=>{
      const url=new URL(req.url);const token=url.pathname.slice(1);
      const filename=url.hostname==='asset' && /^[a-f0-9]{48}$/.test(token) ? grants.get(token) : null;
      if(!filename) return new Response('Not found',{status:404});
      try{return await net.fetch(pathToFileURL(filename).href,{headers:req.headers});}catch{return new Response('Missing media',{status:404});}
    });
    window=new BrowserWindow({width:1480,height:1000,minWidth:1060,minHeight:760,backgroundColor:'#101217',
      title:'LocalCut AI · AI 자동 영상 편집기',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
    window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    window.webContents.on('will-navigate',(event,url)=>{if(!trustedSender(url,rendererFile,devUrl))event.preventDefault();});
    window.webContents.session.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    updateController=new UpdateController(require('electron-updater').autoUpdater,app.isPackaged?updateConfig:{},s=>window?.webContents.send('update',s),()=>busy);
    ipcMain.handle('localcut',request);
    window.on('close',event=>{
      if(busy){event.preventDefault();dialog.showMessageBox(window,{type:'info',title:'작업 진행 중',message:'영상 처리가 끝난 뒤 프로그램을 종료해 주세요. 원본 영상은 변경되지 않습니다.'});}
    });
    if(devUrl) await window.loadURL(devUrl);else await window.loadFile(rendererFile);
    if(app.isPackaged) updateController.action('check').catch(()=>{});
  });
  app.on('window-all-closed',()=>app.quit());
}
