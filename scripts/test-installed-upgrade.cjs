// Real Windows installed baseline -> candidate update, including NSIS and restart.
// Only the transport is a loopback HTTP server before public release approval.
const {_electron:electron}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {createReadStream}=require('node:fs');
const {Transform}=require('node:stream');
const http=require('node:http');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const asar=require('@electron/asar');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const hash=async filename=>crypto.createHash('sha256').update(await fs.readFile(filename)).digest('hex');
const ps=code=>{
 const result=spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(code,'utf16le').toString('base64')],{encoding:'utf8',windowsHide:true});
 if(result.status!==0)throw new Error(result.stderr);return result.stdout.trim();
};
async function until(check,label,timeout=120000){
 const end=Date.now()+timeout;
 while(Date.now()<end){try{if(await check())return;}catch{}await delay(1000);}
 throw new Error('Timed out: '+label);
}
async function main(){
 assert.equal(process.platform,'win32','Use an isolated Windows runner');
 assert.equal(process.env.GITHUB_ACTIONS,'true','Never run an installer-upgrade fixture on a personal PC');
 const exe=path.resolve(process.env.LOCALCUT_TEST_INSTALLED_EXE);
 const version=process.env.LOCALCUT_CANDIDATE_VERSION||require('../package.json').version;
 const live=process.env.LOCALCUT_LIVE_GITHUB==='1';
 const baseline=process.env.LOCALCUT_BASE_VERSION||'0.2.0';
 const directory=path.resolve('test-results/installed-upgrade');await fs.mkdir(directory,{recursive:true});
 const feed=path.resolve(process.env.LOCALCUT_CANDIDATE_DIR,'release');
 let corrupt=true,served=0;
 const server=http.createServer(async(req,res)=>{
  try{
   const filename=decodeURIComponent(new URL(req.url,'http://localhost').pathname.slice(1));
   if(!['latest.yml',`LocalCut-AI-${version}-x64-Setup.exe`,`LocalCut-AI-${version}-x64-Setup.exe.blockmap`].includes(filename)){res.writeHead(404).end();return;}
   const file=path.join(feed,filename);const stat=await fs.stat(file);
   res.writeHead(200,{'Content-Length':stat.size,'Content-Type':'application/octet-stream','Cache-Control':'no-store'});
   if(req.method==='HEAD'){res.end();return;}
   const stream=createReadStream(file);
   if(filename.endsWith('.exe')){
    served++;let first=true;
    stream.pipe(new Transform({transform(chunk,_encoding,done){if(corrupt&&first){chunk[0]^=1;first=false;}done(null,chunk);}})).pipe(res);
   }else stream.pipe(res);
  }catch{if(!res.headersSent)res.writeHead(500);res.end();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let app;
 try{
  app=await electron.launch({executablePath:exe,args:[],timeout:60000});
  let page=await app.firstWindow();page.setDefaultTimeout(60000);
  await page.waitForFunction(()=>!!window.localcut);
  const before=await page.evaluate(()=>window.localcut.call('health'));assert.equal(before.version,baseline);
  const data=await app.evaluate(({app})=>app.getPath('userData'));
  const sentinel=path.join(data,'workspace/models/upgrade-test/keep.bin');await fs.mkdir(path.dirname(sentinel),{recursive:true});await fs.writeFile(sentinel,'LocalCut upgrade preservation fixture; not model weights');
  const media=path.join(path.dirname(exe),'resources/media/ffmpeg.exe');
  const sample=path.join(directory,'업데이트 원본.mp4');
  const made=spawnSync(media,['-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=6','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',sample],{encoding:'utf8'});assert.equal(made.status,0,made.stderr);
  const sourceHash=await hash(sample),modelHash=await hash(sentinel);
  const project=await page.evaluate(source=>window.localcut.call('import',{path:source}),sample);
  const edited=await page.evaluate(id=>window.localcut.call('edit',{id,changes:{captions:[{id:'keep-caption',start:0.2,end:1.5,text:'검토한 한국어 자막 유지'}],cuts:[{id:'keep-cut',start:2,end:3,enabled:true,review:false,reason:'사용자가 검토한 컷',confidence:1}],settings:{fontFamily:'nanum',fontSize:46,highlightWords:'한국어'}}}),project.id);
  await page.reload();
  await page.getByRole('button',{name:'모델 · 업데이트',exact:true}).click();
  await until(async()=>!['idle','checking'].includes((await page.evaluate(()=>window.localcut.call('updateStatus'))).status),'initial online check');
  if(!live){
  await app.evaluate(({app},url)=>{
   const {createRequire}=process.mainModule.require('node:module');
   const updater=createRequire(app.getAppPath()+'/package.json')('electron-updater').autoUpdater;
   updater.setFeedURL({provider:'generic',url});updater.disableDifferentialDownload=true;
  },`http://127.0.0.1:${server.address().port}/`);
  await page.getByRole('button',{name:'업데이트 확인',exact:true}).click();
  await page.getByRole('button',{name:'다운로드',exact:true}).waitFor();
  await page.getByRole('button',{name:'다운로드',exact:true}).click();
  await until(async()=>(await page.evaluate(()=>window.localcut.call('updateStatus'))).status==='error','corrupted update rejected');
  const rejected=await page.evaluate(()=>window.localcut.call('updateStatus'));
  assert.match(rejected.message,/sha512|checksum|digest/i,'Checksum failure must reject altered installer');
  assert.equal((await page.evaluate(()=>window.localcut.call('health'))).version,baseline);
  corrupt=false;
  }
  await page.getByRole('button',{name:'업데이트 확인',exact:true}).click();
  await page.getByRole('button',{name:'다운로드',exact:true}).click();
  await page.getByRole('button',{name:'설치하고 재시작',exact:true}).waitFor({timeout:180000});
  await page.screenshot({path:path.join(directory,'download-complete.png'),fullPage:true});
  page.once('dialog',dialog=>dialog.accept());
  const closed=app.waitForEvent('close',{timeout:180000});
  await page.getByRole('button',{name:'설치하고 재시작',exact:true}).click().catch(error=>{if(!/closed|destroyed/i.test(error.message))throw error;});
  await closed;app=null;
  const selected=`Get-Process | Where-Object { $_.Path -eq '${exe.replaceAll("'","''")}' }`;
  await until(async()=>{
   const archive=path.join(path.dirname(exe),'resources/app.asar');asar.uncache(archive);
   const installed=JSON.parse(asar.extractFile(archive,'package.json').toString());
   return installed.version===version&&Number(ps(`@(${selected} | Where-Object { $_.MainWindowHandle -ne 0 }).Count`))>0;
  },'upgraded app automatic restart',180000);
  // The restarted app has no Playwright debugger. Close it through its own window,
  // then reconnect by launching the same installed executable and default userData.
  ps(`${selected} | ForEach-Object { [void]$_.CloseMainWindow() }`);
  await until(async()=>Number(ps(`@(${selected}).Count`))===0,'graceful close after automatic restart');
  app=await electron.launch({executablePath:exe,args:[],timeout:60000});
  page=await app.firstWindow();page.setDefaultTimeout(60000);await page.waitForFunction(()=>!!window.localcut);
  const after=await page.evaluate(()=>window.localcut.call('health'));assert.equal(after.version,version);
  assert.equal(await app.evaluate(({app})=>app.getPath('userData')),data);
  const saved=await page.evaluate(id=>window.localcut.call('get',{id}),project.id);
  for(const key of ['captions','cuts'])assert.deepEqual(saved.project[key],edited.project[key],key+' must be preserved');
  const previousSettings={...edited.project.settings};
  if(saved.project.settings.captionSizeMode!==undefined&&previousSettings.captionSizeMode===undefined){
   previousSettings.captionSizeMode='manual';
  }
  assert.deepEqual(saved.project.settings,previousSettings,'Saved subtitle size and other settings must be preserved');
  assert.equal(await hash(sample),sourceHash);assert.equal(await hash(sentinel),modelHash);
  const rendered=await page.evaluate(id=>window.localcut.call('render',{id}),project.id);
  assert.ok(Math.abs(rendered.project.output.duration-5)<0.2,'Upgraded engine must render preserved cut');
  await page.getByRole('button',{name:/업데이트 원본/}).click();
  await page.locator('.source-panel .preview-seek-controls button:not(:disabled)').first().waitFor();
  await page.getByRole('button',{name:'원본 영상 5초 앞으로',exact:true}).click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.source-panel video').currentTime-5)<.1);
  await page.getByRole('button',{name:'원본 영상 5초 뒤로',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.source-panel video').currentTime===0);
  await page.locator('.result-panel .preview-seek-controls button:not(:disabled)').first().waitFor();
  await page.getByRole('button',{name:'편집 결과 5초 앞으로',exact:true}).click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.result-panel video').currentTime-5)<.1);
  await page.screenshot({path:path.join(directory,'after-upgrade.png'),fullPage:true});
  const report={passed:true,from:before.version,to:after.version,fiveSecondSeekPassed:true,transport:live?'live public GitHub provider':'loopback HTTP candidate feed; public GitHub not yet published',realWindowsInstaller:true,corruptPayloadRejected:!live,automaticRestartObserved:true,userDataPreserved:true,sourcePreserved:true,modelFolderSentinelPreserved:true,realModelWeightsTested:false,captionCutsSettingsPreserved:true,renderedDuration:rendered.project.output.duration,downloadRequests:served,build:process.env.LOCALCUT_CANDIDATE_SHA,harness:process.env.GITHUB_SHA};
  await fs.writeFile(path.join(directory,'result.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
 }finally{if(app)await app.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
