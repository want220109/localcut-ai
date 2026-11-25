import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import type {Audit,Caption,ClipSelection,Cut,CutPreview,Health,HistoryLists,LongformDraft,LongformResult,Progress,Project,ProjectResult,SequenceConnection,SequenceCutPreview,SequenceOutlineDraft,SequenceOutlinePreview,Settings,TranscriptOperation,Update} from './types';
import './styles.css';
import {BasicSubtitleControls,SubtitleControls} from './SubtitleControls';
import {EditSummary} from './EditSummary';
import {PreviewSeekControls} from './PreviewSeekControls';
import {CaptionFramePreview} from './CaptionFramePreview';
import {LongformEditor} from './LongformEditor';
import {TranscriptEditor} from './TranscriptEditor';
import {CutConnectionPreview} from './CutConnectionPreview';
import {SequenceEditor} from './SequenceEditor';
import subtitleCatalog from '../../subtitles/presets.json';
import {version as appVersion} from '../../package.json';

const bridge=window.localcut;
type Mp4Save={id:string;state:'saving'|'saved'|'canceled'|'error';message:string};
const saveError=(error:unknown)=>String(error instanceof Error?error.message:error).replace(/^Error invoking remote method 'localcut': (?:Error: )?/,'');
const time=(s:number)=>{const ms=Math.floor(Math.max(0,s)*10);return `${Math.floor(ms/600).toString().padStart(2,'0')}:${(Math.floor(ms/10)%60).toString().padStart(2,'0')}.${ms%10}`;};
function Icon({name,size=20}:{name:string;size?:number}) {
 const paths:Record<string,React.ReactNode>={
  cut:<><path d="m9 9 11 11M9 15l11-11M5 4l4 5"/><circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/></>,
  upload:<><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/></>,
  play:<path d="m9 5 11 7-11 7Z"/>,
  folder:<path d="M3 6h6l2 3h10v11H3Z"/>,
  spark:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="m20 2 1 2 2 1-2 1-1 2-1-2-2-1 2-1Z"/></>,
  check:<path d="m5 12 4 4L20 5"/>,
  settings:<><path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/></>,
  shield:<><path d="m12 3 8 3v6c0 4-8 9-8 9s-8-5-8-9V6Z"/><path d="m8 11 3 3 5-5"/></>,
  clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  download:<><path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/></>,
  restore:<><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></>,
  film:<><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/></>,
  arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>,
  text:<><path d="M4 5h16M12 5v15M8 20h8"/></>,
 };
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.film}</svg>;
}
function App(){
 const [project,setProject]=useState<Project|null>(null),[audit,setAudit]=useState<Audit|null>(null);
 const [health,setHealth]=useState<Health|null>(null),[history,setHistory]=useState<HistoryLists>({recent:[],hidden:[]});
 const [viewHidden,setViewHidden]=useState(false);
 const [busy,setBusy]=useState(false),[progress,setProgress]=useState<Progress>({percent:0,message:''});
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[tab,setTab]=useState<'cuts'|'captions'|'transcript'|'longform'>('cuts');
 const [mp4Save,setMp4Save]=useState<Mp4Save|null>(null);
 const [productionRunning,setProductionRunning]=useState(false);
 const [autoReview,setAutoReview]=useState<{id:string;request:number}|null>(null);
 const [connection,setConnection]=useState<{clip?:CutPreview;error?:string}|null>(null);
 const [settingsOpen,setSettingsOpen]=useState(false),[model,setModel]=useState('small'),[command,setCommand]=useState('');
 const [update,setUpdate]=useState<Update>({status:'unconfigured',message:'배포 저장소 연결 전',channel:'stable'});
 const [sourceTime,setSourceTime]=useState(0),[drag,setDrag]=useState(false),[dirtyCaption,setDirtyCaption]=useState<Caption|null>(null);
 const [manualStart,setManualStart]=useState('0'),[manualEnd,setManualEnd]=useState('1');
 const sourceVideo=useRef<HTMLVideoElement>(null),outputVideo=useRef<HTMLVideoElement>(null);
 async function call<T>(action:string,data:Record<string,unknown>={}):Promise<T>{if(!bridge)throw new Error('Electron 데스크톱 앱으로 실행해 주세요. 브라우저 미리보기에서는 로컬 파일 기능을 사용할 수 없습니다.');return await bridge.call(action,data) as T;}
 async function refresh(){const [h,list,u]=await Promise.all([call<Health>('health'),call<HistoryLists>('historyLists'),call<Update>('updateStatus')]);setHealth(h);setHistory(list);setUpdate(u);}
 useEffect(()=>{
  if(!bridge)return;
  const off=bridge.onProgress(setProgress),offUpdate=bridge.onUpdate(setUpdate);
  refresh().catch(e=>setError(String(e.message||e)));
  return ()=>{off();offUpdate();};
 },[]);
 useEffect(()=>{setDirtyCaption(null);setSourceTime(0);},[project?.id]);
 useEffect(()=>setConnection(null),[project?.id,project?.revision,tab]);
 function accept(result:ProjectResult|Project){if('project' in result){setProject(result.project);setAudit(result.audit);if(result.message)setNotice(result.message);}else{setProject(result);setAudit(null);}}
 async function task(fn:()=>Promise<void>){if(busy)return;setBusy(true);setError('');setNotice('');setProgress({percent:0,message:'준비 중'});try{await fn();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 async function load(){await task(async()=>{const p=await call<Project|ProjectResult|null>('pick');if(p){accept(p);setViewHidden(false);setHistory(await call<HistoryLists>('historyLists'));}});}
 async function open(id:string){await task(async()=>{accept(await call<ProjectResult>('get',{id}));});}
 async function changeHistory(operation:'hide'|'restore'|'clear'|'restoreAll',id?:string){
  await task(async()=>{
   setHistory(await call<HistoryLists>('changeHistory',{operation,id}));
   setNotice(operation==='restore'||operation==='restoreAll'?'최근 작업 목록에 복원했습니다.':'목록에서 숨겼습니다. 숨긴 작업에서 복원할 수 있습니다.');
  });
 }
 async function edit(changes:Record<string,unknown>){if(!project)return;await task(async()=>{accept(await call<ProjectResult>('edit',{id:project.id,changes}));});}
 async function changeSequence(action:string,fields:Record<string,unknown>){
  if(!project||busy)return false;
  let saved=false;
  await task(async()=>{
   const result=await call<ProjectResult>(action,{id:project.id,revision:project.revision,...fields});
   accept(result);
   const failures=result.captionFailures??result.editFailures;
   if(failures?.length){
    const operation=result.editFailures?'편집점을 찾지 못한':'자막을 생성하지 못한';
    setError(`${operation} 영상 ${failures.length}개 · ${failures[0]}`);
   }
   saved=true;
  });
  return saved;
 }
 async function readSequence<T>(action:string,fields:Record<string,unknown>):Promise<T|null>{
  if(!project||busy)return null;
  outputVideo.current?.pause();
  let result:T|null=null;
  await task(async()=>{result=await call<T>(action,{id:project.id,revision:project.revision,...fields});});
  return result;
 }
 async function editTranscript(operation:TranscriptOperation,lineIds:string[]){
  if(!project)return;
  await task(async()=>accept(await call<ProjectResult>('editTranscript',{id:project.id,revision:project.revision,operation,lineIds})));
 }
 async function previewConnection(cutId:string){
  if(!project||busy)return;
  setConnection(null);
  sourceVideo.current?.pause();
  outputVideo.current?.pause();
  await task(async()=>{
   try{
    const clip=await call<CutPreview>('cutPreview',{id:project.id,revision:project.revision,cutId});
    setConnection({clip});
   }catch(error){setConnection({error:saveError(error)});}
  });
 }
 async function setting<K extends keyof Settings>(key:K,value:Settings[K]){await edit({settings:{[key]:value}});}
 async function operate(action:string){if(!project)return;await task(async()=>{accept(await call<ProjectResult>(action,{id:project.id,model}));if(action==='analyze'||action==='undo')setDirtyCaption(null);setHistory(await call<HistoryLists>('historyLists'));});}
 async function analyze(){if(!project)return;if(project.analyzed&&!window.confirm('재분석하면 현재 편집 구간과 자막 수정이 새 분석 결과로 바뀝니다. 계속할까요?'))return;await operate('analyze');}
 async function createLongform(targetSeconds:number){
  if(!project)return null;
  let draft:LongformDraft|null=null;
  await task(async()=>{
   const result=await call<LongformResult>('longformDraft',{id:project.id,targetSeconds,model});
   if(result.project&&result.audit){
    accept({project:result.project,audit:result.audit});
    setHistory(await call<HistoryLists>('historyLists'));
   }
   draft=result.draft;
  });
  return draft;
 }
 async function applyLongform(draft:LongformDraft,selected:string[]){
  if(!project)return false;
  let applied=false;
  await task(async()=>{
   const result=await call<ProjectResult>('applyLongform',{id:project.id,targetSeconds:draft.targetSeconds,revision:draft.revision,selected});
   accept(result);
   applied=true;
  });
  return applied;
 }
 function showAutoReview(id:string){
  setAutoReview(previous=>({id,request:(previous?.request??0)+1}));
 }
 async function produceLongform(){
  if(!project||busy)return;
  const {id,revision}=project;
  await task(async()=>{
   setProductionRunning(true);
   setMp4Save(null);
   outputVideo.current?.pause();
   try{
    const result=await call<ProjectResult>('autoLongform',{id,revision,model});
    accept(result);
    showAutoReview(id);
    setHistory(await call<HistoryLists>('historyLists'));
   }catch(error){
    // Analysis can be saved even when the complete preview could not be rendered.
    try{accept(await call<ProjectResult>('get',{id}));}catch{}
    throw error;
   }finally{
    setProductionRunning(false);
   }
  });
 }
 async function save(kind:string){
  if(!project||busy)return;
  const {id}=project;
  await task(async()=>{
   if(kind==='mp4')setMp4Save({id,state:'saving',message:'저장 위치를 선택하면 파일을 저장합니다.'});
   let filename:string|null;
   try{filename=await call<string|null>('export',{id,kind});}
   catch(error){
    if(kind!=='mp4')throw error;
    setMp4Save({id,state:'error',message:saveError(error)});
    accept(await call<ProjectResult>('get',{id}));
    return;
   }
   if(kind==='mp4')setMp4Save(filename?{id,state:'saved',message:filename}:{id,state:'canceled',message:'저장을 취소했습니다.'});
   else if(filename)setNotice('저장했습니다: '+filename);
   accept(await call<ProjectResult>('get',{id}));
  });
 }
 async function revealMp4(saved=false){
  if(!project||busy)return;
  const {id}=project;
  await task(async()=>{
   try{await call('reveal',{id,kind:'mp4',saved});}
   catch(error){setMp4Save({id,state:'error',message:saveError(error)});}
  });
 }
 async function updateAction(operation:string,channel?:string){await task(async()=>{setUpdate(await call<Update>('update',{operation,channel}));});}
 async function installModel(importModel=false){await task(async()=>{await call('model',{model,consent:!importModel,import:importModel});await refresh();setNotice('모델 준비가 완료되었습니다. 이제 인터넷 없이 분석할 수 있습니다.');});}
 async function drop(e:React.DragEvent){e.preventDefault();setDrag(false);const files=Array.from(e.dataTransfer.files);if(!files.length||!bridge||busy)return;await task(async()=>{accept(files.length===1?await bridge.dropped(files[0]):await bridge.droppedFiles(files));setViewHidden(false);setHistory(await call<HistoryLists>('historyLists'));});}
 function seek(value:number){if(sourceVideo.current)sourceVideo.current.currentTime=value;setSourceTime(value);}
 async function toggle(c:Cut){if(project)await edit({cuts:project.cuts.map(x=>x.id===c.id?{...x,enabled:!x.enabled}:x)});}
 async function changeBounds(c:Cut,key:'start'|'end',value:string){const number=Number(value);if(!project||!Number.isFinite(number))return;await edit({cuts:project.cuts.map(x=>x.id===c.id?{...x,[key]:number,review:true,reason:'사용자가 편집 구간을 조정함'}:x)});}
 async function addManual(){if(!project)return;const c:Cut={id:crypto.randomUUID().replaceAll('-','').slice(0,12),start:Number(manualStart),end:Number(manualEnd),kind:'manual',reason:'사용자가 직접 지정한 삭제 구간',confidence:1,review:false,enabled:true};await edit({cuts:[...project.cuts,c].sort((a,b)=>a.start-b.start)});}
 const p=project,sourceDuration=p?.source.duration||0,outDuration=audit?.outputDuration??sourceDuration;
 const removed=p?.clips?0:Math.max(0,sourceDuration-outDuration),pending=p?.cuts.filter(c=>c.review&&!c.enabled).length||0;
 const selectedModel=health?.models.find(m=>m.id===model),stale=!!p?.output&&p.output.revision!==p.revision;
 const disabled=busy||!bridge;
 const autoReady=!!p?.autoLongform&&!!p.outputUrl&&!stale;
 const autoNeedsModel=p?.clips
  ?p.clips.some(clip=>clip.enabled&&clip.source.hasAudio&&!clip.speechReady&&
    ((!clip.analyzed&&!clip.captions.length)||clip.cuts===undefined))
  :!!p?.source.hasAudio&&!p.analyzed&&!p.transcript.length;
 const autoReviewRequest=autoReview?.id===p?.id?autoReview?.request??0:0;
 const saveFeedback=mp4Save?.id===p?.id?mp4Save:null;
 const subtitleSettings=p?.settings||({
  ...subtitleCatalog.defaults,captionSizeMode:'auto',captionScale:'short-edge',fontSize:subtitleCatalog.automaticSizes.standard,
  color:'#FFFFFF',outline:2,background:false,position:'bottom'
 } as Settings);
 const historyItems=viewHidden?history.hidden:history.recent;
 const resultPanel=(exportBlocked=false)=>(<div className="panel result-panel"><div className="section-title"><h2>{!p?.clips&&<span className="number-label">02</span>} {p?.autoLongform?'롱폼 초안 재생':'편집 결과'}</h2>{p?.output&&<span className={'status-pill '+(stale?'warning':'')}>{stale?'수정 내용은 저장 시 반영':p.autoLongform?'초안 준비 완료':'출력 완료'}</span>}</div>
       {p?.outputUrl?<><div className="video-stage"><video key={p.output?.path} ref={outputVideo} src={p.outputUrl} controls preload="metadata"/><span className="video-label result">{stale?'수정 전 미리보기':p.autoLongform?'롱폼 초안':'EDITED'}</span></div><PreviewSeekControls videoRef={outputVideo} mediaKey={p.outputUrl} label="편집 결과"/></>:<div className="result-empty"><div className="result-placeholder"><Icon name="play" size={23}/></div><h3>{busy?'당신의 이야기를 다듬고 있어요':'완성될 이야기를 기다리는 중'}</h3><p>{p?.clips?'MP4 저장을 누르면 포함한 영상을 순서대로 합쳐 한 파일로 저장합니다.':p?.analyzed?'편집 구간을 확인하고 MP4를 출력해 주세요.':'AI 분석 후 편집 결과를 여기서 확인하세요.'}</p></div>}
       <div className="result-footer"><div><span>예상 완성 길이</span><strong>{p?time(outDuration):'--:--'} {removed>0&&<small>−{time(removed)}</small>}</strong></div><div className="button-row">
        {!!p?.outputUrl&&!stale&&<button className="quiet" disabled={disabled} onClick={()=>revealMp4()}><Icon name="folder" size={15}/> 출력 파일 위치</button>}
        <button className={p?.clips?"primary":"secondary"} disabled={disabled||!p||exportBlocked} onClick={()=>save('mp4')}><Icon name="download" size={15}/>{saveFeedback?.state==='saving'?'저장 중…':p?.autoLongform?'최종 MP4 저장':'MP4 저장'}</button>
       </div></div>
       {saveFeedback&&<div className={'export-feedback '+saveFeedback.state} role={saveFeedback.state==='error'?'alert':'status'}>
        {saveFeedback.state==='saved'&&<strong>MP4 저장 완료</strong>}
        <span>{saveFeedback.message}</span>
        {saveFeedback.state==='saved'&&<button className="secondary" disabled={disabled} onClick={()=>revealMp4(true)}>저장한 파일 위치</button>}
       </div>}
      </div>);
 return <div className="app-shell">
  <aside className="sidebar">
   <a className="brand" href="#" onClick={e=>e.preventDefault()}><span className="brand-mark"><Icon name="cut" size={23}/></span><span>LocalCut<span className="brand-ai">AI</span></span></a>
   <div className="workspace-label">나의 편집 공간</div>
   <button className="nav-item active" onClick={()=>setSettingsOpen(false)}><Icon name="film"/>자동 영상 편집<span className="nav-dot"/></button>
   <button className="nav-item" onClick={()=>{setViewHidden(false);document.getElementById('history')?.scrollIntoView({behavior:'smooth'});}}><Icon name="folder"/>최근 작업</button>
   <button className={'nav-item '+(settingsOpen?'selected':'')} onClick={()=>setSettingsOpen(!settingsOpen)}><Icon name="settings"/>모델 · 업데이트</button>
   <div className="sidebar-divider"/>
   <div className="history-heading" id="history">{viewHidden?'숨긴 작업':'최근 작업'} <span>{historyItems.length}</span></div>
   <div className="history-actions">
    {viewHidden?<><button className="quiet" onClick={()=>setViewHidden(false)}>최근 작업 보기</button>
      {!!history.hidden.length&&<button className="quiet" disabled={disabled} onClick={()=>changeHistory('restoreAll')}>모두 복원</button>}</>:
     <><button className="quiet" onClick={()=>setViewHidden(true)}>숨긴 작업 {history.hidden.length?`(${history.hidden.length})`:''}</button>
      {!!history.recent.length&&<button className="quiet" disabled={disabled}
       onClick={()=>changeHistory('clear')}>목록 비우기</button>}</>}
   </div>
   <div className="history-list" aria-label={viewHidden?'숨긴 작업 목록':'최근 작업 목록'} role="region">
    {historyItems.length?historyItems.map(h=><div key={h.id} className="history-row">
     {viewHidden?<span className="history-hidden-name" title={h.name}>{h.name}</span>:
      <button disabled={disabled} onClick={()=>open(h.id)} className={'history-item '+(p?.id===h.id?'current':'')} title={h.name}>
       <Icon name="film" size={16}/><span>{h.name}<small>{new Date(h.updatedAt*1000).toLocaleDateString('ko-KR')} · {h.analyzed?'분석 완료':'새 작업'}</small></span>
      </button>}
     <button className="quiet history-action" disabled={disabled} onClick={()=>changeHistory(viewHidden?'restore':'hide',h.id)}
      aria-label={h.name+(viewHidden?' 복원':' 목록에서 제거')} title={viewHidden?'최근 작업에 복원':'목록에서 제거'}>{viewHidden?'복원':'×'}</button>
    </div>):<p className="history-empty">{viewHidden?'숨긴 작업이 없습니다.':'최근 작업이 없습니다.'}</p>}
   </div>
   <div className="local-note"><span className="local-dot"/>내 PC에서 안전하게<small>원본 영상은 업로드되지 않습니다.</small><div><Icon name="shield" size={14}/> LOCAL FIRST</div></div>
   <div className="version">LocalCut AI <span>v{health?.version||appVersion}</span></div>
  </aside>
  <main>
   <header><div className="breadcrumbs">워크스페이스 <span>/</span> <strong>자동 영상 편집</strong></div><div className="header-right"><span className="offline-badge"><span/>로컬 처리</span><button className="icon-button" aria-label="설정 열기" onClick={()=>setSettingsOpen(!settingsOpen)}><Icon name="settings" size={19}/></button><div className="avatar">LC</div></div></header>
   <div className="page-content">
    <div className="page-heading"><div><div className="eyebrow">YOUR STORY, BEAUTIFULLY CUT.</div><h1>편집은 AI에게, 이야기는 당신에게.</h1><p>원본을 불러오세요. 대화의 흐름을 살려 자연스러운 한 편으로 만듭니다.</p></div><span className="private-pill"><Icon name="shield" size={16}/> 원본 보존 · 유료 API 없음</span></div>
    {!bridge&&<div className="banner info">데스크톱 앱 화면 미리보기입니다. 영상 처리와 저장은 Electron 앱에서 사용할 수 있습니다.</div>}
    {error&&<div className="banner error" role="alert"><strong>작업을 완료하지 못했습니다.</strong><span>{error}</span><button onClick={()=>setError('')} aria-label="오류 닫기">×</button></div>}
    {notice&&<div className="banner success" role="status">{notice}<button onClick={()=>setNotice('')} aria-label="안내 닫기">×</button></div>}
    {settingsOpen&&<section className="settings-panel panel"><div className="section-title"><h2><Icon name="settings" size={18}/> 모델과 업데이트</h2><button className="quiet" onClick={()=>setSettingsOpen(false)}>닫기</button></div><div className="settings-columns"><div><h3>로컬 한국어 음성 모델</h3><p>모델 파일만 외부에서 다운로드합니다. 영상과 대본은 전송하지 않습니다.</p><label>음성인식 모델<select value={model} disabled={busy} onChange={e=>setModel(e.target.value)}>{(health?.models||[{id:'small',label:'한국어 권장 · small',sizeMB:490,ready:false},{id:'tiny',label:'속도 우선 · tiny',sizeMB:76,ready:false}]).map(m=><option key={m.id} value={m.id}>{m.label} · 약 {m.sizeMB} MB {m.ready?'· 준비됨':''}</option>)}</select></label><div className="model-status">{selectedModel?.ready?'● 로컬 모델 준비 완료':'○ 모델을 먼저 준비해 주세요'}</div><div className="button-row"><button className="secondary" disabled={disabled||selectedModel?.ready} onClick={()=>installModel()}>다운로드에 동의하고 설치</button><button className="quiet" disabled={disabled} onClick={()=>installModel(true)}>오프라인 폴더 가져오기</button></div><p className="small muted">{health?.cpuNote||'CPU에서도 실행할 수 있습니다. 긴 영상은 영상 길이보다 오래 걸릴 수 있습니다.'}<br/>GPU 사용은 CUDA 드라이버·라이브러리 준비 상태에 따라 달라집니다.</p></div><div><h3>프로그램 업데이트</h3><label>배포 채널<select disabled={busy||update.status==='downloading'||update.status==='downloaded'} value={update.channel} onChange={e=>updateAction('check',e.target.value)}><option value="stable">안정 버전</option><option value="beta">테스트 버전</option></select></label><p>{update.message}</p>{update.version&&<span className="tag">v{update.version}</span>}{update.notes&&<pre className="release-notes">{update.notes}</pre>}{update.status==='downloading'&&<progress max={100} value={update.percent||0}/>}<div className="button-row"><button className="secondary" disabled={disabled||update.status==='unconfigured'} onClick={()=>updateAction('check')}>업데이트 확인</button>{update.status==='available'&&<button className="secondary" disabled={disabled} onClick={()=>updateAction('download')}>다운로드</button>}{update.status==='downloaded'&&<button className="primary" disabled={disabled} onClick={()=>{if(window.confirm('작업은 자동 저장되어 있습니다. 업데이트를 설치하고 다시 시작할까요?'))updateAction('install');}}>설치하고 재시작</button>}</div><p className="small muted">편집 중에는 설치하지 않습니다. 업데이트 후에도 작업 기록과 모델은 유지됩니다.</p></div></div></section>}
    {p&&<section className="panel auto-production" aria-label="유튜브 롱폼 자동 제작">
     <div className="section-title">
      <h2><Icon name="spark" size={18}/> 유튜브 롱폼 자동 제작</h2>
      {autoReady?<button className="primary" disabled={disabled} onClick={()=>showAutoReview(p.id)}>초안 보기</button>
       :autoNeedsModel&&!selectedModel?.ready?<button className="primary" disabled={disabled}
        onClick={()=>{setSettingsOpen(true);window.scrollTo(0,0);}}>한국어 음성 모델 준비</button>
       :<button className="primary" disabled={disabled} onClick={produceLongform}>
        {productionRunning?'자동 제작 중…':p.autoLongform?'초안 다시 만들기':'자동 제작'}</button>}
     </div>
     <div className="sequence-body">
      {productionRunning?<div className="sequence-progress" role="status">
       <span>{progress.message} · {Math.round(progress.percent)}%</span><progress max={100} value={progress.percent}/>
      </div>:<p className="small muted">{autoReady
        ?'초안을 재생하고, 필요한 수정이 끝나면 최종 MP4를 저장하세요.'
        :autoNeedsModel&&!selectedModel?.ready?'음성이 있는 영상을 분석하려면 음성 모델을 한 번 준비해 주세요.'
        :p.autoLongform?'현재 편집 내용으로 전체 초안을 다시 재생할 수 있습니다.'
        :'자막, 컷 편집, 롱폼 구성과 음량 보정을 적용한 초안을 만듭니다.'}</p>}
     </div>
    </section>}
    {p?.clips?
     <SequenceEditor key={p.id} project={p} disabled={disabled} progress={busy&&!productionRunning?progress:null} duration={outDuration} formatTime={time} autoReviewRequest={autoReviewRequest}
      edit={async(rows:ClipSelection[])=>{await changeSequence('editSequence',{rows});}}
      preview={async id=>(await readSequence<{url:string}>('sequencePreview',{clipId:id}))?.url??null}
      connection={id=>readSequence<SequenceConnection>('sequenceConnection',{clipId:id})}
      analyzeAll={async()=>{await changeSequence('sequenceAnalyzeAll',{model});}}
      analyzeEdits={async()=>{await changeSequence('sequenceAnalyzeEdits',{model});}}
      previewCut={(clipId,cutId,range)=>readSequence<SequenceCutPreview>('sequenceCutPreview',{clipId,cutId,...range})}
      adjustCut={(clipId,cutId,range)=>changeSequence('sequenceAdjustCut',{clipId,cutId,...range})}
      setCut={async(clipId,cutId,enabled)=>{await changeSequence('sequenceSetCut',{clipId,cutId,enabled});}}
      loadOutline={fresh=>readSequence<SequenceOutlineDraft>('sequenceOutlineDraft',{fresh})}
      previewOutline={(rowId,fresh)=>readSequence<SequenceOutlinePreview>('sequenceOutlinePreview',{rowId,fresh})}
      applyOutline={(rows,fresh)=>changeSequence('sequenceApplyOutline',{rows,fresh})}
      clearOutline={()=>changeSequence('sequenceClearOutline',{})}
      modelReady={!!selectedModel?.ready} showModels={()=>{setSettingsOpen(true);window.scrollTo(0,0);}}
      analyze={async clipId=>{await changeSequence('sequenceAnalyze',{clipId,model});}}
      saveCaption={(clipId,caption)=>changeSequence('sequenceCaption',{clipId,captionId:caption.id,text:caption.text})}
      changeSettings={async settings=>{await edit({settings});}} render={()=>operate('render')} undo={()=>operate('undo')} replace={load} saveSubtitles={()=>save('srt')} result={resultPanel}/>
    :<>
    <div className="step-bar"><div className="step complete"><b>{p?<Icon name="check" size={13}/>:1}</b>영상 불러오기</div><span/><div className={'step '+(p?'complete':'')}><b>{p?.analyzed?<Icon name="check" size={13}/>:2}</b>AI 분석 · 편집</div><span/><div className={'step '+(p?.analyzed?'complete':'')}><b>3</b>검수 · 내보내기</div></div>
    <div className="editor-grid">
     <section className="media-column">
      <div className="panel source-panel"><div className="section-title"><h2><span className="number-label">01</span> 원본 영상</h2>{p&&<button className="quiet" disabled={disabled} onClick={load}><Icon name="folder" size={14}/> 영상 변경</button>}</div>
       {p?<><div className="video-stage"><video ref={sourceVideo} src={p.sourceUrl} controls preload="metadata" onTimeUpdate={e=>setSourceTime(e.currentTarget.currentTime)}/><span className="video-label">{p.preview?'ORIGINAL · 호환 미리보기':'ORIGINAL'}</span></div><PreviewSeekControls videoRef={sourceVideo} mediaKey={p.sourceUrl} label="원본 영상" onSeek={setSourceTime}/><div className="file-summary"><div className="file-icon"><Icon name="film"/></div><div><strong title={p.name}>{p.name}</strong><p>{p.source.width} × {p.source.height} <i/> {p.source.fps.toFixed(2)} fps <i/> {(p.source.bytes/1024/1024).toFixed(1)} MB</p></div><span className="duration">{time(p.source.duration)}</span></div></>:<button className={'dropzone '+(drag?'dragging':'')} disabled={disabled} onClick={load} onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)} onDrop={drop}><div className="upload-orbit"><div><Icon name="upload" size={29}/></div></div><h3>이야기가 담긴 영상을 불러오세요</h3><p>영상 하나 또는 여러 개를 드래그하거나 선택하세요.</p><span className="select-file"><Icon name="folder" size={15}/> 영상 선택하기</span><small>MP4, MOV, AVI, MKV <span>·</span> 원본 파일은 그대로 보존됩니다</small></button>}
      </div>
      {resultPanel()}
     </section>
     <aside className="controls-column panel"><div className="section-title"><h2><Icon name="spark" size={18}/> 편집 설정</h2><span className="tag">AI ASSIST</span></div><div className="controls-body"><label className="field-label">어떤 분위기로 편집할까요?</label><div className="style-options">{([{id:'basic',title:'기본 편집',sub:'자연스러운 흐름, 편안한 호흡',icon:'film',label:'RECOMMENDED'},{id:'fast',title:'빠른 편집',sub:'간결한 컷, 경쾌한 전개',icon:'spark',label:''},{id:'shorts',title:'쇼츠 · 릴스',sub:'세로 화면, 핵심 장면 중심',icon:'play',label:'9:16'}] as const).map(s=><button key={s.id} disabled={disabled||!p} onClick={()=>edit({style:s.id,settings:{aspect:s.id==='shorts'?'9:16':'source',zoom:s.id==='basic'?1:s.id==='fast'?1.08:1.05}})} className={'style-option '+((p?.style||'basic')===s.id?'chosen':'')}><span className="style-icon"><Icon name={s.icon} size={20}/></span><span><strong>{s.title}{s.label&&<em>{s.label}</em>}</strong><small>{s.sub}</small></span><span className="radio"/></button>)}</div>
      <div className="field-heading"><span><Icon name="text" size={16}/> 자동 자막</span><label className="switch"><input type="checkbox" aria-label="자막 사용" disabled={disabled||!p} checked={p?.settings.subtitles??true} onChange={e=>setting('subtitles',e.target.checked)}/><span/></label></div>
      <SubtitleControls settings={subtitleSettings} disabled={disabled||!p} aspect={p?.settings.aspect==="source"?p.source.aspect:(p?.settings.aspect||"source")} onChange={changes=>edit({settings:changes})}/>
      <BasicSubtitleControls settings={subtitleSettings} disabled={disabled||!p} onChange={changes=>edit({settings:changes})}/>
      <div className="control-divider"/><label className="field-label">출력 설정</label><div className="two-fields"><label>해상도<select disabled={disabled||!p} value={p?.settings.resolution||'source'} onChange={e=>setting('resolution',e.target.value as Settings['resolution'])}><option value="source">원본 유지</option><option value="1080">1080p</option><option value="720">720p</option></select></label><label>화면 비율<select disabled={disabled||!p} value={p?.settings.aspect||'source'} onChange={e=>setting('aspect',e.target.value as Settings['aspect'])}><option value="source">원본 유지</option><option value="16:9">16:9 가로</option><option value="9:16">9:16 세로</option><option value="1:1">1:1 정사각</option></select></label></div><label className="quality-label">영상 품질<select disabled={disabled||!p} value={p?.settings.quality||'balanced'} onChange={e=>setting('quality',e.target.value as Settings['quality'])}><option value="high">고화질 · 큰 파일</option><option value="balanced">균형 · 권장</option><option value="small">작은 파일</option></select></label><div className="audio-options"><label className="checkbox"><input type="checkbox" disabled={disabled||!p} checked={p?.settings.normalize??true} onChange={e=>setting('normalize',e.target.checked)}/> 음량 균일화</label><label className="checkbox"><input type="checkbox" disabled={disabled||!p} checked={p?.settings.denoise??true} onChange={e=>setting('denoise',e.target.checked)}/> 배경 소음 완화</label></div><label className="quality-label">줌 효과<select disabled={disabled||!p} value={p?.settings.zoom||1} onChange={e=>setting('zoom',Number(e.target.value))}>{[1,1.05,1.08,1.1,1.15].map(n=><option key={n} value={n}>{n===1?'사용 안 함':`${Math.round((n-1)*100)}% 확대`}</option>)}</select></label>{p?.settings.aspect==='9:16'&&<p className="small muted">중앙 기준으로 좌우를 잘라 세로 화면을 만듭니다. 중요한 피사체가 잘리지 않는지 확인해 주세요.</p>}
      </div><div className="controls-actions"><button className="primary analyze-button" disabled={disabled||!p} onClick={analyze}><Icon name="spark" size={18}/>{p?.analyzed?'다시 분석·편집점 생성':'AI 분석·편집점 생성'}<Icon name="arrow" size={16}/></button><p className="local-caption"><Icon name="shield" size={12}/> 모델 준비 후 오프라인으로 분석합니다</p>
      <button className="secondary longform-open" disabled={disabled||!p} onClick={()=>{setTab('longform');document.getElementById('edit-review')?.scrollIntoView({block:'start'});}}>유튜브 롱폼 초벌 편집</button>
     </div></aside>
    </div>
    {(!productionRunning&&(busy||p?.analyzed))&&<div className="progress-panel panel"><div><span className={busy?'spinner':'completed-mark'}>{!busy&&<Icon name="check" size={17}/>}</span><div><strong>{busy?progress.message:'분석 결과가 준비되었습니다'}</strong><p>{busy?'작업 내용은 PC 안에서 처리됩니다. 잠시 기다려 주세요.':`${p?.cuts.filter(c=>c.enabled).length||0}개 삭제 구간 · ${pending}개 검토 제안 · 모든 변경은 자동 저장됩니다.`}</p></div><b>{busy?`${Math.round(progress.percent)}%`:'READY'}</b></div><progress max={100} value={busy?progress.percent:100}/></div>}
    {p&&audit?.cutSummary&&<EditSummary summary={audit.cutSummary} project={p} formatTime={time}/>}
    <section className="review-panel panel" id="edit-review"><div className="section-title"><h2><Icon name="cut" size={19}/> 편집 검수</h2><div className="button-row"><span className="autosave"><span/> 자동 저장</span><button className="quiet" disabled={disabled||!p} onClick={()=>operate('undo')}><Icon name="restore" size={14}/> 이전 변경 되돌리기</button><button className="primary small-button" disabled={disabled||!p} onClick={()=>operate('render')}><Icon name="download" size={15}/> MP4 출력</button></div></div>
     {p?<><div className="timeline"><div className="timeline-ruler">{[0,.25,.5,.75,1].map(r=><span key={r}>{time(sourceDuration*r)}</span>)}</div><div className="timeline-track" role="slider" aria-label="원본 영상 타임라인" tabIndex={0} aria-valuemin={0} aria-valuemax={sourceDuration} aria-valuenow={sourceTime} onKeyDown={e=>{if(e.key==='ArrowRight')seek(Math.min(sourceDuration,sourceTime+1));if(e.key==='ArrowLeft')seek(Math.max(0,sourceTime-1));}} onClick={e=>{const rect=e.currentTarget.getBoundingClientRect();seek((e.clientX-rect.left)/rect.width*sourceDuration);}}><div className="timeline-base"/>{p.cuts.map(c=><div key={c.id} title={`${time(c.start)}–${time(c.end)} ${c.reason}`} className={'timeline-cut '+(c.enabled?'removed':'review')} style={{left:`${100*c.start/sourceDuration}%`,width:`${100*(c.end-c.start)/sourceDuration}%`}}/>)}{p.scenes.map(s=><div key={s} className="scene-tick" style={{left:`${100*s/sourceDuration}%`}}/>)}<div className="playhead" style={{left:`${100*sourceTime/sourceDuration}%`}}/></div><div className="timeline-legend"><span><i className="keep"/>보존</span><span><i className="remove"/>삭제</span><span><i className="review"/>보존 중인 제안</span><span><i className="scene"/>장면 전환</span><small>원본 기준 시간 · 클릭하여 이동</small></div></div>
      {p.warnings.length>0&&<details className="analysis-notes"><summary>분석 참고사항 {p.warnings.length}개</summary>{p.warnings.map((w,i)=><p key={i}>{w}</p>)}</details>}
      <div className="review-tabs"><button className={tab==='cuts'?'active':''} onClick={()=>setTab('cuts')}>편집 구간 <span>{p.cuts.length}</span></button><button className={tab==='captions'?'active':''} onClick={()=>setTab('captions')}>자막 수정 <span>{p.captions.length}</span></button><button className={tab==='transcript'?'active':''} onClick={()=>setTab('transcript')}>대본 편집</button><button className={tab==='longform'?'active':''} onClick={()=>setTab('longform')}>롱폼 구성</button></div>
      {connection&&(tab==='cuts'||tab==='transcript')&&<CutConnectionPreview {...connection} formatTime={time} close={()=>setConnection(null)}/>}
      <div hidden={tab!=='longform'}><LongformEditor key={p.id} project={p} disabled={disabled||tab!=='longform'} formatTime={time} createDraft={createLongform} applyDraft={applyLongform}/></div>
      {tab==='cuts'&&<><div className="cut-list">{p.cuts.length?p.cuts.map(c=><div className="cut-row" key={c.id}><button className="time-link" onClick={()=>seek(c.start)}>{time(c.start)}<small>{time(c.end)}</small></button><div className="cut-reason"><strong>{c.kind==='silence'?'침묵':c.kind==='speech_gap'?'발화 공백':c.kind==='retake'?'반복 발언':c.kind==='highlight'?'쇼츠 구성':c.kind==='manual'?'직접 지정':'말실수 후보'}<span className={'status-pill '+(c.review?'warning':'')}>{c.enabled?'삭제 예정':'보존 중'}</span></strong><p>{c.reason}</p></div><label className="bound-input">시작 (초)<input aria-label={`${c.id} 시작`} type="number" step="0.1" min="0" max={sourceDuration} disabled={disabled} defaultValue={c.start} key={`${c.id}-a-${c.start}`} onBlur={e=>{if(Number(e.target.value)!==c.start)changeBounds(c,'start',e.target.value);}}/></label><label className="bound-input">종료 (초)<input aria-label={`${c.id} 종료`} type="number" step="0.1" min="0" max={sourceDuration} disabled={disabled} defaultValue={c.end} key={`${c.id}-b-${c.end}`} onBlur={e=>{if(Number(e.target.value)!==c.end)changeBounds(c,'end',e.target.value);}}/></label><button className={c.enabled?'quiet restore-button':'secondary'} disabled={disabled} onClick={()=>toggle(c)}>{c.enabled?'복원':'삭제 적용'}</button>{c.enabled&&c.start>0&&c.end<sourceDuration&&<button className="quiet" disabled={disabled} onClick={()=>previewConnection(c.id)}>연결부 보기</button>}</div>):<div className="inline-empty">{p.analyzed?'안전하게 삭제할 구간을 찾지 못했습니다. 영상을 보존했습니다.':'영상을 분석하면 편집점과 삭제 이유가 여기에 표시됩니다.'}</div>}</div><div className="manual-controls"><span>직접 삭제 구간 추가</span><input aria-label="수동 삭제 시작" type="number" step="0.1" value={manualStart} onChange={e=>setManualStart(e.target.value)}/><span>–</span><input aria-label="수동 삭제 종료" type="number" step="0.1" value={manualEnd} onChange={e=>setManualEnd(e.target.value)}/><span>초</span><button className="secondary" disabled={disabled} onClick={addManual}>구간 추가</button></div></>}
      {tab==='captions'&&<div className="captions-editor"><div className="caption-list">{p.captions.length?p.captions.map(c=><button className={dirtyCaption?.id===c.id?'selected':''} key={c.id} onClick={()=>{if(dirtyCaption&&dirtyCaption.text!==p.captions.find(x=>x.id===dirtyCaption.id)?.text&&!window.confirm('저장하지 않은 자막 수정을 버릴까요?'))return;setDirtyCaption({...c});seek(c.start);}}><span>{time(c.start)}</span>{c.text}</button>):<p className="inline-empty">음성 분석 후 자막이 표시됩니다.</p>}</div><div className="caption-edit">{dirtyCaption?<><label>자막 내용<textarea aria-label="자막 내용" maxLength={10000} value={dirtyCaption.text} onChange={e=>setDirtyCaption({...dirtyCaption,text:e.target.value})}/></label><div className="two-fields"><label>시작 (초)<input type="number" step="0.01" value={dirtyCaption.start} onChange={e=>setDirtyCaption({...dirtyCaption,start:Number(e.target.value)})}/></label><label>종료 (초)<input type="number" step="0.01" value={dirtyCaption.end} onChange={e=>setDirtyCaption({...dirtyCaption,end:Number(e.target.value)})}/></label></div><button className="secondary" disabled={disabled} onClick={()=>edit({captions:p.captions.map(c=>c.id===dirtyCaption.id?{...dirtyCaption,textEdited:true}:c)})}>자막 수정 저장</button><CaptionFramePreview key={p.id+":"+dirtyCaption.id} projectId={p.id} revision={p.revision} caption={dirtyCaption} paused={disabled} formatTime={time}/></>:<p className="muted">왼쪽에서 수정할 자막을 선택하세요.</p>}<p className="small muted">시간은 원본 영상 기준입니다. 삭제 구간을 반영한 자막은 출력 시 자동 동기화됩니다. 자동 보정은 공백·문장 부호 정리에 한정됩니다.</p><button className="quiet" disabled={disabled||!p.output} onClick={()=>save('srt')}>출력된 SRT 저장</button></div></div>}
      {tab==='transcript'&&<><TranscriptEditor key={p.id} project={p} disabled={disabled} duration={outDuration} formatTime={time} seek={value=>{seek(value);sourceVideo.current?.scrollIntoView({block:'center'});}} edit={editTranscript} preview={previewConnection}/><details className="transcript-audit"><summary>대본 비교와 출력 검증</summary><div className="transcript-comparison">{audit&&(audit.importantRemoved>0||audit.partial.length>0)&&<div className="banner warning">중요 문장 {audit.importantRemoved}개 삭제 · 문장 일부 삭제 {audit.partial.length}개. 출력 전 원본과 확인해 주세요.</div>}<div><h3>원본 대본</h3><pre>{audit?.before||'인식된 대본이 없습니다.'}</pre></div><div><h3>완전히 보존된 문장</h3><pre>{audit?.after||'보존된 대본이 없습니다.'}</pre></div>{!!audit?.partial.length&&<div className="removed-transcript"><h3>일부만 보존된 문장</h3>{audit.partial.map(s=><p key={s.id}>{s.text} <small>({Math.round(s.retained*100)}% 보존)</small></p>)}</div>}{!!audit?.removed.length&&<div className="removed-transcript"><h3>삭제된 문장</h3>{audit.removed.map(s=><p key={s.id}>{s.important?'⚠ ':''}{s.text}</p>)}</div>}<button className="quiet" disabled={disabled||!p.output} onClick={()=>save('report')}>출력 검증 보고서 저장</button></div></details></>}
      <form className="command-bar" onSubmit={e=>{e.preventDefault();if(!command.trim())return;task(async()=>{accept(await call<ProjectResult>('command',{id:p.id,text:command}));setCommand('');});}}><Icon name="spark" size={20}/><input aria-label="자연어 수정 요청" disabled={disabled} value={command} onChange={e=>setCommand(e.target.value)} placeholder="예: 자막을 더 크게 해줘 · 잘라낸 대화를 다시 살려줘"/><span>기본 명령</span><button type="submit" disabled={disabled||!command.trim()} aria-label="수정 요청 적용"><Icon name="arrow" size={18}/></button></form>
     </>:<div className="review-empty"><Icon name="cut" size={28}/><p>AI가 제안한 편집점을 확인하고, 당신의 감각으로 마무리하세요.</p><span>구간 복원 · 자막 수정 · 대본 비교 · 자연어 수정</span></div>}
    </section>
    </>}
    <footer><span><Icon name="shield" size={13}/> 당신의 영상은 당신의 PC 안에.</span><span>H.264 / AAC <i/> MP4 OUTPUT</span></footer>
   </div>
  </main>
 </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
