// Runs the real Electron preload -> IPC -> Python -> FFmpeg path. No mocked bridge.
const {_electron:electron}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
async function checkSeekButtons(page,panel,label){
 const selector=panel+' video';
 await page.waitForFunction(selector=>{const v=document.querySelector(selector);return v?.readyState>=1&&Number.isFinite(v.duration);},selector);
 const back=page.getByRole('button',{name:label+' 5초 뒤로',exact:true});
 const forward=page.getByRole('button',{name:label+' 5초 앞으로',exact:true});
 await page.locator(panel+' .preview-seek-controls button:not(:disabled)').first().waitFor();
 const duration=await page.locator(selector).evaluate(v=>{v.pause();v.currentTime=1;return v.duration;});
 await back.click();
 await page.waitForFunction(selector=>document.querySelector(selector).currentTime===0,selector);
 assert.equal(await page.locator(selector).evaluate(v=>v.paused),true,'Seeking must not autoplay');
 await forward.focus();await forward.press('Enter');
 await page.waitForFunction(({selector,time})=>Math.abs(document.querySelector(selector).currentTime-time)<.05,{selector,time:Math.min(5,duration)}).catch(async error=>{console.error('Seek diagnostic',await page.evaluate(selector=>{const v=document.querySelector(selector);return {time:v.currentTime,duration:v.duration,ready:v.readyState,error:v.error?.message,active:document.activeElement?.outerHTML,buttons:[...document.querySelectorAll('.preview-seek-controls button')].map(b=>({text:b.textContent,disabled:b.disabled}))};},selector));throw error;});
 await forward.click();
 await page.waitForFunction(({selector,time})=>Math.abs(document.querySelector(selector).currentTime-time)<.05,{selector,time:duration});
 await back.click();
 await page.waitForFunction(({selector,time})=>Math.abs(document.querySelector(selector).currentTime-time)<.05,{selector,time:Math.max(0,duration-5)});
 // While playing, a backward seek must keep playing; no edit or output changes.
 await page.locator(selector).evaluate(async v=>{v.currentTime=1;await v.play();});
 await back.click();assert.equal(await page.locator(selector).evaluate(v=>v.paused),false);
 await page.locator(selector).evaluate(v=>{v.pause();v.currentTime=0;});
 console.log(label+' five-second seek: clamp, keyboard and playback state passed');
}
async function expectRevealed(app,expected){
 await app.evaluate(async (_electron,filename)=>{
  for(let attempt=0;attempt<100;attempt++){
   if(globalThis.__revealedExport===filename)return;
   await new Promise(resolve=>setTimeout(resolve,25));
  }
  throw new Error('Explorer did not receive the expected file: '+filename);
 },expected);
}
async function checkLongform(app,page,sample,testRoot){
 const source=path.join(testRoot,'롱폼 편집 검증.mp4');
 await fs.copyFile(sample,source);
 const {id}=await page.evaluate(file=>window.localcut.call('import',{path:file}),source);
 await page.reload();
 await page.getByRole('button',{name:/롱폼 편집 검증/}).click();
 await page.getByRole('button',{name:'유튜브 롱폼 초벌 편집',exact:true}).click();
 const frame=page.getByRole('region',{name:'유튜브 롱폼 초벌 편집',exact:true});
 const generate=frame.getByRole('button',{name:'초벌 편집안 만들기',exact:true});
 await generate.click();
 await frame.getByText(/대사 근거가 부족해/).waitFor();
 const empty=await page.evaluate(id=>window.localcut.call('get',{id}),id);
 assert.equal(empty.project.analyzed,true);
 assert.equal(empty.audit.outputDuration,6);
 assert.equal(empty.project.output,null);
 // Controlled saved transcript fixture, without downloading real model weights.
 const userData=await app.evaluate(({app})=>app.getPath('userData'));
 const projectPath=path.join(userData,'workspace','jobs',id,'project.json');
 const project=JSON.parse(await fs.readFile(projectPath,'utf8'));
 project.scenes=[];
 project.transcript=[
  {id:'intro',start:.2,end:1.3,text:'오늘은 여기에 왔습니다',confidence:.98},
  {id:'first-take',start:2,end:2.65,text:'이제 거리를 한 번 둘러보고 올게요',confidence:.98},
  {id:'second-take',start:3,end:3.65,text:'이제 거리를 한 번 둘러보고 올게요',confidence:.98},
  {id:'ending',start:4.8,end:5.6,text:'정리하면 오늘 여행은 여기서 마칩니다',confidence:.98},
 ];
 project.captions=project.transcript.map(line=>({...line}));
 project.captions[0]={...project.captions[0],text:'오늘은 부산에 왔습니다',textEdited:true};
 project.cuts=[{id:'ambient',start:4,end:4.65,kind:'speech_gap',reason:'현장음 확인 후보',confidence:.6,review:true,enabled:false}];
 await fs.writeFile(projectPath,JSON.stringify(project),'utf8');
 await page.getByRole('button',{name:/롱폼 편집 검증/}).click();
 await frame.getByLabel('목표 길이 (초)').fill('5.2');
 await generate.click();
 await frame.getByText('오늘은 부산에 왔습니다',{exact:true}).waitFor();
 await frame.getByRole('button',{name:'마무리 원본 보기',exact:true}).click();
 await page.waitForFunction(()=>Math.abs(document.querySelector('.longform-preview video').currentTime-4.8)<.05);
 const keep=frame.getByRole('checkbox',{name:/같은 발언이 바로 이어집니다/});
 const ambient=frame.getByRole('checkbox',{name:/현장음 확인 후보/});
 assert.equal(await keep.isChecked(),true);
 assert.equal(await ambient.isChecked(),false);
 const pending=await page.evaluate(id=>window.localcut.call('get',{id}),id);
 assert.equal(pending.audit.outputDuration,6);
 await frame.getByLabel('목표 길이 (초)').fill('5.1');
 await frame.getByText(/다시 만들어 주세요/).waitFor();
 assert.equal(await frame.getByRole('button',{name:'선택한 컷 적용 (1)',exact:true}).isDisabled(),true);
 await generate.click();
 await frame.getByRole('button',{name:'선택한 컷 적용 (1)',exact:true}).click();
 await frame.getByText(/1개 컷을 적용했습니다/).waitFor();
 await page.getByRole('button',{name:'MP4 출력',exact:true}).click();
 await page.locator('.result-panel .status-pill').filter({hasText:'출력 완료'}).waitFor({timeout:60000});
 const result=await page.evaluate(id=>window.localcut.call('get',{id}),id);
 assert.equal(result.project.cuts.filter(c=>c.enabled).length,1);
 assert.equal(result.project.cuts.find(c=>c.id==='ambient').enabled,false);
 assert.ok(Math.abs(result.project.output.duration-5.29)<.12);
 console.log('Long-form draft, source preview, explicit approval and rendered duration passed');
}
async function main(){
 const root=path.resolve(__dirname,'..');
 const testRoot=path.join(root,'test-results',process.env.LOCALCUT_PACKAGED_EXE?'installed-electron':'electron');await fs.mkdir(testRoot,{recursive:true});
 const sample=path.join(testRoot,'실제 테스트.mp4');
 const ffmpeg=process.env.LOCALCUT_MEDIA_DIR?path.join(process.env.LOCALCUT_MEDIA_DIR,'ffmpeg.exe'):'ffmpeg';
 const created=spawnSync(ffmpeg,['-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=6','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',sample],{encoding:'utf8'});
 if(created.status!==0) throw new Error(created.stderr);
 const sourceOriginalHash=crypto.createHash('sha256').update(await fs.readFile(sample)).digest('hex');
 const args=[...(process.env.LOCALCUT_PACKAGED_EXE?[]:['.']),`--user-data-dir=${path.join(testRoot,'appdata-'+Date.now())}`];
 if(process.platform==='linux'){args.push('--no-sandbox','--disable-gpu');if(!process.env.DISPLAY)args.push('--ozone-platform=headless');}
 const options={args,cwd:root,executablePath:process.env.LOCALCUT_PACKAGED_EXE||undefined,timeout:30000,env:{...process.env,XDG_CACHE_HOME:path.join(testRoot,'cache'),GSETTINGS_BACKEND:'memory',LOCALCUT_PYTHON:process.env.LOCALCUT_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')}};
 let app=await electron.launch(options);
 try{
  const page=await app.firstWindow({timeout:30000});page.setDefaultTimeout(30000);
  await app.evaluate(({BrowserWindow})=>{const window=BrowserWindow.getAllWindows()[0];window.focus();window.webContents.focus();});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.getByRole('heading',{name:'편집은 AI에게, 이야기는 당신에게.'}).waitFor();
  await page.waitForFunction(()=>!!window.localcut);
  await page.screenshot({path:path.join(testRoot,'01-empty.png'),fullPage:true});
  const health=await page.evaluate(()=>window.localcut.call('health'));
  console.log('Electron health passed');
  if(health.version!==require('../package.json').version)throw new Error('Health response mismatch');
  const p=await page.evaluate(file=>window.localcut.call('import',{path:file}),sample);
  // A real imported project is then selected through the user's history UI.
  await page.reload();
  await page.getByRole('button',{name:/실제 테스트/}).click();
  await page.getByText('실제 테스트',{exact:true}).first().waitFor();
  const sizeField=page.getByLabel('자막 크기',{exact:true});
  await sizeField.locator('option:checked').filter({hasText:'자동 · 64px'}).waitFor({state:'attached'});
  await page.getByRole('button',{name:/쇼츠 · 릴스/}).click();
  await sizeField.locator('option:checked').filter({hasText:'자동 · 80px'}).waitFor({state:'attached'});
  await page.getByRole('button',{name:/기본 편집/}).click();
  await sizeField.locator('option:checked').filter({hasText:'자동 · 64px'}).waitFor({state:'attached'});
  await page.waitForFunction(()=>document.querySelector('video')?.readyState>=1);
  // Verify the custom local-media protocol, metadata, and video decoding.
  const media=await page.evaluate(async()=>{
    const video=document.querySelector('video');video.currentTime=1;
    await Promise.race([new Promise(resolve=>video.addEventListener('seeked',resolve,{once:true})),new Promise((_,reject)=>setTimeout(()=>reject(new Error('Video seek timed out: '+JSON.stringify({readyState:video.readyState,networkState:video.networkState,error:video.error?.message}))),10000))]);
    return {duration:video.duration,width:video.videoWidth,error:video.error?.message};
  });
  if(media.width!==640||media.error)throw new Error('Media preview failed: '+JSON.stringify(media));
  console.log('Local media playback passed');
  const beforeSeek=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  await checkSeekButtons(page,'.source-panel','원본 영상');
  const afterSeek=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  assert.equal(afterSeek.project.revision,beforeSeek.project.revision,'Preview seek must not edit the project');
  await page.getByRole('button',{name:'AI 분석·편집점 생성',exact:true}).click();
  await page.getByText('분석 결과가 준비되었습니다').waitFor({timeout:30000});
  await page.evaluate(id=>window.localcut.call('edit',{id,changes:{captions:[{id:'caption-fixture',start:.2,end:1.5,text:'오늘 영상의 핵심을 보여드립니다'}]}}),p.id);
  await page.reload();
  await page.getByRole('button',{name:/실제 테스트/}).click();
  await page.getByRole('button',{name:/^자막 수정 /}).click();
  await page.getByRole('button',{name:/오늘 영상의 핵심을 보여드립니다/}).click();
  const frame=page.getByRole('img',{name:'현재 자막과 출력 설정을 적용한 정지 화면',exact:true});
  await frame.waitFor();
  const firstFrame=await frame.getAttribute('src');
  await page.getByLabel('자막 내용',{exact:true}).fill('미리 보는 수정 자막');
  await page.waitForFunction(previous=>{
   const image=document.querySelector('.caption-frame-image img');
   return image?.src!==previous&&image?.complete&&image.naturalWidth>0;
  },firstFrame);
  const editedFrame=await frame.getAttribute('src');
  await sizeField.selectOption('160');
  await page.waitForFunction(previous=>{
   const image=document.querySelector('.caption-frame-image img');
   return image?.src!==previous&&image?.complete&&image.naturalWidth>0;
  },editedFrame);
  const previewOnly=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  assert.equal(previewOnly.project.settings.fontSize,160);
  assert.equal(previewOnly.project.captions[0].text,'오늘 영상의 핵심을 보여드립니다','Preview must not save the draft');
  assert.equal(previewOnly.project.output,null,'Preview must not render an MP4');
  await page.getByRole('button',{name:/^편집 구간 /}).click();
  console.log('Caption still preview, unsaved editing and 160px size passed');
  await page.getByLabel('자막 프리셋').selectOption('shorts_pop');
  await page.waitForFunction(()=>!document.querySelector('[aria-label="자막 프리셋"]').disabled);
  const styled=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  if(styled.project.settings.aspect!=='source'||styled.project.captions[0].text!=='오늘 영상의 핵심을 보여드립니다')throw new Error('Preset changed video framing or edited words');
  await page.getByRole('button',{name:'9:16 화면 비율 적용',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('[aria-label="자막 프리셋"]').disabled);
  await page.getByLabel('강조 단어',{exact:true}).fill('핵심');
  await page.getByLabel('강조 단어',{exact:true}).press('Tab');
  await page.waitForFunction(()=>!document.querySelector('[aria-label="자막 프리셋"]').disabled);
  await page.evaluate(()=>document.fonts.ready);
  const faces=await page.evaluate(async()=>{
    const specs=['700 20px "LocalCut Nanum"','400 20px "LocalCut Nanum"','400 20px "LocalCut Black Han"'];
    return Promise.all(specs.map(async spec=>(await document.fonts.load(spec,'한국어 자막')).map(face=>face.status)));
  });
  if(faces.some(list=>!list.length||list.some(status=>status!=='loaded')))throw new Error('Bundled UI font failed to load');
  // Real UI editing, persistence and rendering.
  await page.getByLabel('수동 삭제 시작').fill('2');
  await page.getByLabel('수동 삭제 종료').fill('4');
  await page.getByRole('button',{name:'구간 추가',exact:true}).click();
  await page.getByText('사용자가 직접 지정한 삭제 구간').waitFor();
  await page.getByRole('button',{name:'MP4 출력',exact:true}).click();
  await page.locator('.result-panel .status-pill').filter({hasText:'출력 완료'}).waitFor({timeout:60000});
  const result=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  if(Math.abs(result.project.output.duration-4)>.2)throw new Error('Wrong output duration');
  const sourcePosition=await page.locator('.source-panel video').evaluate(v=>v.currentTime);
  await checkSeekButtons(page,'.result-panel','편집 결과');
  assert.equal(await page.locator('.source-panel video').evaluate(v=>v.currentTime),sourcePosition,'Result seek must not move the source');
  await page.getByLabel('자연어 수정 요청').fill('잘라낸 대화를 다시 살려줘');
  await page.getByRole('button',{name:'수정 요청 적용'}).click();
  await page.getByText('삭제 구간을 모두 복원했습니다.').waitFor();
  // Saving a stale preview must render the current revision first, then copy that file.
  const exportTarget=path.join(testRoot,'최신 편집 저장.mp4');
  await app.evaluate(({dialog},filename)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:filename});},exportTarget);
  await page.getByRole('button',{name:'MP4 저장',exact:true}).click();
  await page.locator('.export-feedback.saved').filter({hasText:exportTarget}).waitFor({timeout:60000});
  const latest=await page.evaluate(id=>window.localcut.call('get',{id}),p.id);
  if(latest.project.output.revision!==latest.project.revision || Math.abs(latest.project.output.duration-6)>.2 || latest.project.output.path===result.project.output.path)throw new Error('Stale output was exported');
  if(latest.audit.cutSummary.appliedCount!==0 || latest.audit.cutSummary.removedDuration!==0)throw new Error('Cut summary did not reflect restoration');
  const digest=data=>crypto.createHash('sha256').update(data).digest('hex');
  if(digest(await fs.readFile(exportTarget))!==digest(await fs.readFile(latest.project.output.path)))throw new Error('Saved file is not the latest output');
  await app.evaluate(({shell})=>{shell.showItemInFolder=filename=>{globalThis.__revealedExport=filename;};});
  await page.getByRole('button',{name:'저장한 파일 위치',exact:true}).click();
  await expectRevealed(app,exportTarget);
  const unavailable=path.join(testRoot,'missing-save-folder','export.mp4');
  await app.evaluate(({dialog},filename)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:filename});},unavailable);
  await page.getByRole('button',{name:'MP4 저장',exact:true}).click();
  await page.locator('.export-feedback.error').filter({hasText:'선택한 저장 위치를 찾을 수 없습니다.'}).waitFor();
  await page.getByRole('button',{name:'출력 파일 위치',exact:true}).click();
  await expectRevealed(app,latest.project.output.path);
  const noExtension=path.join(testRoot,'확장자 보완 '+Date.now());
  await app.evaluate(({dialog},filename)=>{dialog.showSaveDialog=async(_window,options)=>{
   globalThis.__saveDefault=options.defaultPath;return {canceled:false,filePath:filename};
  };},noExtension);
  await page.getByRole('button',{name:'MP4 저장',exact:true}).click();
  await page.locator('.export-feedback.saved').filter({hasText:noExtension+'.mp4'}).waitFor();
  assert.equal(digest(await fs.readFile(noExtension+'.mp4')),digest(await fs.readFile(exportTarget)));
  const {defaultPath,downloads}=await app.evaluate(({app})=>({defaultPath:globalThis.__saveDefault,downloads:app.getPath('downloads')}));
  assert.equal(path.dirname(defaultPath),downloads);
  // A derived filename did not receive the OS dialog's overwrite confirmation.
  await fs.writeFile(noExtension+'.mp4','existing export');
  await page.getByRole('button',{name:'MP4 저장',exact:true}).click();
  await page.locator('.export-feedback.error').filter({hasText:'같은 이름의 파일이 있습니다.'}).waitFor();
  assert.equal(await fs.readFile(noExtension+'.mp4','utf8'),'existing export');
  const originalHash=sourceOriginalHash;
  // Original-file protection is enforced by main, even for direct IPC requests.
  await app.evaluate(({dialog},filename)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:filename});},sample);
  const overwrite=await page.evaluate(async id=>{try{await window.localcut.call('export',{id,kind:'mp4'});return '';}catch(err){return err.message;}},p.id);
  if(!overwrite.includes('원본 영상에는 저장할 수 없습니다.'))throw new Error('Original-file export guard failed');
  // The save dialog holds the main-process lock: edits cannot race a file export.
  await app.evaluate(({dialog})=>{globalThis.__saveWaiter=null;dialog.showSaveDialog=()=>new Promise(resolve=>{globalThis.__saveWaiter=resolve;});});
  const pendingSave=page.evaluate(id=>window.localcut.call('export',{id,kind:'mp4'}),p.id);
  await app.evaluate(()=>new Promise((resolve,reject)=>{let tries=0;const timer=setInterval(()=>{if(globalThis.__saveWaiter){clearInterval(timer);resolve();}else if(++tries>500){clearInterval(timer);reject(new Error('Save dialog did not open'));}},20);}));
  const racedEdit=await page.evaluate(async id=>{try{await window.localcut.call('edit',{id,changes:{settings:{fontSize:50}}});return '';}catch(err){return err.message;}},p.id);
  if(!racedEdit.includes('진행 중인 작업'))throw new Error('Export did not lock edits');
  await app.evaluate(()=>globalThis.__saveWaiter({canceled:true}));
  if(await pendingSave!==null)throw new Error('Canceled save was not canceled');
  if(digest(await fs.readFile(sample))!==originalHash)throw new Error('Original video changed');
  console.log('Latest-revision export, inline failure and recovery, extension handling, source protection, canceled save and edit lock passed');
  await page.screenshot({path:path.join(testRoot,'02-project.png'),fullPage:true});
  // Renderer cannot navigate the Electron window to remote code.
  if(errors.length)throw new Error('Renderer errors: '+errors.join('; '));
  console.log('UI edit and render passed; closing app');
  await app.close();app=null;
  console.log('Reopening application');
  app=await electron.launch(options);
  const reopened=await app.firstWindow({timeout:30000});reopened.setDefaultTimeout(30000);
  console.log('Reopened window ready');
  await reopened.getByRole('button',{name:/실제 테스트/}).click();
  await reopened.locator('video').first().waitFor();
  const saved=await reopened.evaluate(id=>window.localcut.call('get',{id}),p.id);
  if(saved.project.cuts.some(c=>c.enabled)||!saved.project.output||saved.project.settings.fontFamily!=='nanum'||saved.project.settings.highlightWords!=='핵심')throw new Error('Project or subtitle settings were not preserved after full restart');
  await checkLongform(app,reopened,sample,testRoot);
  await fs.writeFile(path.join(testRoot,'result.json'),JSON.stringify({passed:true,fiveSecondSeekPassed:true,restartPassed:true,subtitlePresetsPassed:true,longformPassed:true,latestExportPassed:true,exportLockPassed:true,originalPreserved:true,health,media,projectId:p.id,cutOutput:result.project.output,output:latest.project.output,subtitleSettings:saved.project.settings,rendererErrors:errors},null,2));
  console.log('PASS: real Electron import, local playback, analysis (no audio), manual cut, MP4 render, command, full restart and persistence');
 } finally {if(app)await app.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
