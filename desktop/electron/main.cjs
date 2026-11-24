const {app,BrowserWindow,ipcMain,dialog,protocol,shell} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const {COPYFILE_EXCL} = require('node:fs').constants;
const path = require('node:path');
const crypto = require('node:crypto');
const {mediaResponse} = require('./media.cjs');
const {projectId,inside,validMedia,trustedSender} = require('./policy.cjs');
const {UpdateController} = require('../../updater/controller.cjs');
const updateConfig = require('../../updater/config.json');
protocol.registerSchemesAsPrivileged([{scheme:'local-media',privileges:{standard:true,secure:true,stream:true,supportFetchAPI:true}}]);
app.setName('LocalCut AI');
let window, busy=false, updateController;
const grants=new Map();
const savedExports=new Map();
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
async function statIfPresent(filename) {
  try {return await fs.stat(filename);}
  catch(error) {if(error.code!=='ENOENT') throw error;return null;}
}

function samePath(a,b) {
  return process.platform==='win32' ? a.toLowerCase()===b.toLowerCase() : a===b;
}

async function copyExport(source,output,chosen,extension) {
  const hasExtension=chosen.toLowerCase().endsWith(extension);
  const target=hasExtension?chosen:chosen+extension;
  if(samePath(target,path.resolve(source))) throw new Error('원본 영상에는 저장할 수 없습니다. 다른 이름을 선택해 주세요.');
  const [sourceStat,targetStat]=await Promise.all([statIfPresent(source),statIfPresent(target)]);
  if(sourceStat?.ino && targetStat && sourceStat.dev===targetStat.dev && sourceStat.ino===targetStat.ino) {
    throw new Error('원본 영상에는 저장할 수 없습니다. 다른 이름을 선택해 주세요.');
  }
  if(samePath(target,output)) return output;
  try {
    // Use a sibling temporary file before replacing an approved destination.
    // A name changed after the dialog never overwrites an existing file.
    if(!hasExtension) {
      await fs.copyFile(output,target,COPYFILE_EXCL);
    } else {
      const temporary=path.join(path.dirname(target),'.localcut-save-'+crypto.randomUUID()+'.tmp');
      try {
        await fs.copyFile(output,temporary,COPYFILE_EXCL);
        await fs.rename(temporary,target);
      } finally {
        await fs.rm(temporary,{force:true}).catch(()=>{});
      }
    }
  } catch(error) {
    if(error.code==='ENOSPC'||error.code==='EDQUOT') throw new Error('저장 공간이 부족합니다. 여유 공간이 있는 폴더를 선택해 주세요.');
    if(error.code==='EACCES'||error.code==='EPERM'||error.code==='EBUSY'||error.code==='EROFS') throw new Error('선택한 위치에 쓸 수 없습니다. 파일을 열어 둔 프로그램을 닫거나 다운로드 폴더를 선택해 주세요.');
    if(error.code==='EEXIST') throw new Error('같은 이름의 파일이 있습니다. 확장자를 포함한 파일 이름을 선택하거나 새 이름으로 저장해 주세요.');
    if(error.code==='ENOENT') throw new Error('선택한 저장 위치를 찾을 수 없습니다. 다운로드 폴더를 선택해 주세요.');
    throw error;
  }
  const written=await fs.stat(target);
  if(!written.isFile()||written.size===0) throw new Error('저장한 파일을 확인하지 못했습니다. 출력 파일 위치에서 결과를 확인해 주세요.');
  return target;
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
    const kind=message.kind||'mp4';
    if(!['mp4','srt','report'].includes(kind)) throw new Error('지원하지 않는 저장 형식입니다.');
    // Hold the edit/update-install lock through rendering, the save dialog and file copy.
    // Otherwise an edit during the dialog could export an obsolete result.
    busy=true;
    try {
      const exportKey=`${id}:${kind}`;
      if(action==='reveal' && message.saved===true) {
        const saved=savedExports.get(exportKey);
        if(!saved||!(await statIfPresent(saved))?.isFile()) throw new Error('저장한 파일을 찾을 수 없습니다. 출력 파일 위치를 확인해 주세요.');
        shell.showItemInFolder(saved);
        return true;
      }
      if(action==='export') savedExports.delete(exportKey);
      let {project:p}=await engine({action:'get',id},false);
      if(action==='export' && (!p.output || p.output.revision!==p.revision)) {
        ({project:p}=await engine({action:'render',id},false));
      }
      if(!p.output || p.output.revision!==p.revision) throw new Error('최신 편집 결과를 출력하지 못했습니다. 다시 시도해 주세요.');
      const filename=p.output[kind==='srt'?'srt':kind==='report'?'report':'path'];
      const real=await fs.realpath(filename);
      if(!inside(await fs.realpath(path.join(dataRoot,'jobs',id)),real)) throw new Error('작업 폴더 밖의 파일을 내보낼 수 없습니다.');
      if(action==='reveal') {shell.showItemInFolder(real);return true;}
      const extension=path.extname(real);
      const name=p.name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/,'')||'LocalCut';
      const suggestion=name+(extension==='.mp4'?'-편집':'')+extension;
      const r=await dialog.showSaveDialog(window,{
        title:extension.slice(1).toUpperCase()+' 저장',
        defaultPath:path.join(app.getPath('downloads'),suggestion),
        filters:[{name:extension.slice(1).toUpperCase(),extensions:[extension.slice(1)]}]
      });
      if(r.canceled||!r.filePath) return null;
      const saved=await copyExport(p.source.path,real,path.resolve(r.filePath),extension);
      savedExports.set(exportKey,saved);
      return saved;
    } finally {busy=false;}
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
      try{return await mediaResponse(filename,req);}catch{return new Response('Missing media',{status:404});}
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
