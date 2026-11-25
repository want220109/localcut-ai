import React,{useEffect,useMemo,useRef,useState} from 'react';
import {CaptionFramePreview} from './CaptionFramePreview';
import {SequenceCuts} from './SequenceCuts';
import {SequenceOutline} from './SequenceOutline';
import {BasicSubtitleControls,SubtitleControls} from './SubtitleControls';

const steps=[
 ['import','영상 불러오기'],['captions','자막 생성'],['edit','영상 편집'],['settings','설정 확인'],['save','MP4 저장']
] as const;
type Step=typeof steps[number][0];
const needsCaptions=(clip:Clip)=>!clip.analyzed&&!clip.captions.length;
const captionStatus=(clip:Clip)=>clip.captions.length?`자막 ${clip.captions.length}줄`:clip.analyzed?'인식된 음성 없음':'자막 생성 전';

import type {Caption,Clip,ClipSelection,CutRange,Progress,Project,SequenceConnection,SequenceCutPreview,SequenceOutlineDraft,SequenceOutlinePreview,Settings} from './types';

interface Props {
 project:Project;
 disabled:boolean;
 progress:Progress|null;
 duration:number;
 formatTime:(value:number)=>string;
 edit:(rows:ClipSelection[])=>Promise<void>;
 preview:(clipId:string)=>Promise<string|null>;
 connection:(clipId:string)=>Promise<SequenceConnection|null>;
 analyze:(clipId:string)=>Promise<void>;
 analyzeAll:()=>Promise<void>;
 analyzeEdits:()=>Promise<void>;
 previewCut:(clipId:string,cutId:string,range?:CutRange)=>Promise<SequenceCutPreview|null>;
 adjustCut:(clipId:string,cutId:string,range:CutRange)=>Promise<boolean>;
 setCut:(clipId:string,cutId:string,enabled:boolean)=>Promise<void>;
 loadOutline:(fresh:boolean)=>Promise<SequenceOutlineDraft|null>;
 previewOutline:(rowId:string,fresh:boolean)=>Promise<SequenceOutlinePreview|null>;
 applyOutline:(rows:ClipSelection[],fresh:boolean)=>Promise<boolean>;
 clearOutline:()=>Promise<boolean>;
 modelReady:boolean;
 showModels:()=>void;
 saveCaption:(clipId:string,caption:Caption)=>Promise<boolean>;
 changeSettings:(settings:Partial<Settings>)=>Promise<void>;
 render:()=>void;
 undo:()=>void;
 replace:()=>void;
 saveSubtitles:()=>void;
 result:(exportBlocked?:boolean)=>React.ReactNode;
 autoReviewRequest:number;
}

export function SequenceEditor({project,disabled,progress,duration,formatTime,edit,preview,connection,
 analyze,analyzeAll,analyzeEdits,previewCut,adjustCut,setCut,loadOutline,previewOutline,applyOutline,clearOutline,modelReady,showModels,saveCaption,changeSettings,render,undo,replace,saveSubtitles,result,autoReviewRequest}:Props) {
 const clips=project.clips!;
 const included=clips.filter(item=>item.enabled);
 const [step,setStep]=useState<Step>(project.autoLongform?'save':included.some(needsCaptions)?'captions':'edit');
 const [selected,setSelected]=useState(included[0].id);
 const [previewUrl,setPreviewUrl]=useState('');
 const [connectionData,setConnectionData]=useState<SequenceConnection|null>(null);
 const [connectionUrl,setConnectionUrl]=useState('');
 const [captionId,setCaptionId]=useState<string|null>(null);
 const [draftTexts,setDraftTexts]=useState<Record<string,string>>({});
 const stepBar=useRef<HTMLElement>(null);
 const captionPanel=useRef<HTMLElement>(null);
 const sourcePlayer=useRef<HTMLVideoElement>(null);
 const clip=clips.find(item=>item.id===selected)!;
 const captionKey=(cue:Caption)=>clip.id+':'+cue.id;
 const cue=clip.captions.find(item=>item.id===captionId)||clip.captions[0];
 const key=cue?captionKey(cue):'';
 const editedText=cue?draftTexts[key]??cue.text:'';
 const draft=useMemo(()=>cue?{...cue,text:editedText}:null,[cue,editedText]);
 const dirty=!!cue&&editedText!==cue.text;
 const pending=included.filter(needsCaptions);
 const readyCount=included.length-pending.length;
 const requiresModel=!modelReady&&pending.some(item=>item.source.hasAudio&&!item.speechReady);
 const hasOutline=!!project.sequenceOutline;
 const hasCurrentOutput=project.output?.revision===project.revision;
 const unsavedCount=clips.reduce((count,item)=>count+item.captions.filter(caption=>{
  const draftText=draftTexts[item.id+':'+caption.id];
  return draftText!==undefined&&draftText!==caption.text;
 }).length,0);
 const position=included.findIndex(item=>item.id===selected);
 const next=position>=0?included[position+1]:undefined;

 useEffect(()=>{
  if(autoReviewRequest)setStep('save');
 },[autoReviewRequest]);
 useEffect(()=>{
  if(step==='save'&&autoReviewRequest)document.getElementById('auto-review')?.scrollIntoView({block:'start'});
 },[autoReviewRequest,step]);

 useEffect(()=>{setConnectionData(null);},[project.revision]);
 useEffect(()=>{
  if(!connectionData){setConnectionUrl('');return;}
  const bytes=Uint8Array.from(atob(connectionData.video),c=>c.charCodeAt(0));
  const url=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
  setConnectionUrl(url);
  return ()=>URL.revokeObjectURL(url);
 },[connectionData]);

 function goTo(nextStep:Step) {
  setStep(nextStep);
  stepBar.current?.scrollIntoView({block:'nearest'});
 }
 function order(rows:Clip[]) {
  return edit(rows.map(({id,enabled})=>({id,enabled})));
 }
 function move(from:number,to:number) {
  if(disabled||hasOutline||from===to||from<0||to<0||to>=clips.length)return;
  const rows=clips.slice();
  const [item]=rows.splice(from,1);
  rows.splice(to,0,item);
  void order(rows);
 }
 function selectClip(id:string) {
  if(id===selected)return;
  setSelected(id);
  setCaptionId(null);
  setPreviewUrl('');
  setConnectionData(null);
 }
 async function open(item:Clip) {
  selectClip(item.id);
  setConnectionData(null);setPreviewUrl('');
  setPreviewUrl((await preview(item.id))||'');
 }
 async function openConnection(){
  setPreviewUrl('');
  setConnectionData(await connection(clip.id));
 }
 async function save(){
  if(!draft||!dirty)return;
  if(await saveCaption(clip.id,draft))setDraftTexts(previous=>{
   const remaining={...previous};
   delete remaining[key];
   return remaining;
  });
 }

 function selectCaption(caption:Caption){
  setCaptionId(caption.id);
  setConnectionData(null);
  const player=sourcePlayer.current;
  if(player?.readyState){
   player.pause();
   player.currentTime=caption.start;
  }
 }

 const clipPicker=<label>자막을 볼 클립<select aria-label="자막을 볼 클립" value={selected} disabled={disabled} onChange={e=>selectClip(e.target.value)}>
  {clips.map(item=><option key={item.id} value={item.id}>
   {item.name} · {captionStatus(item)}{item.enabled?'':' · 제외'}
  </option>)}
 </select></label>;
 const framePreview=draft?<CaptionFramePreview key={key} projectId={project.id} revision={project.revision} clipId={clip.id}
     caption={draft} paused={disabled} formatTime={formatTime}/>:null;
 const captions=<section ref={captionPanel} className="panel sequence-caption-panel" aria-label="선택한 클립 자막">
  <div className="section-title"><h2>선택한 클립 자막</h2>
   {needsCaptions(clip)&&<button className="secondary" disabled={disabled||(!modelReady&&clip.source.hasAudio&&!clip.speechReady)}
    onClick={()=>analyze(clip.id)}>클립 자막 만들기</button>}
  </div>
  <div className="sequence-caption-picker">{clipPicker}</div>
  {draft?<div className="captions-editor sequence-caption-grid">
   <div className="caption-list" role="group" aria-label="클립 자막 목록">
    {clip.captions.map(item=><button type="button" key={item.id} disabled={disabled}
     className={item.id===draft.id?'selected':''} aria-pressed={item.id===draft.id} onClick={()=>selectCaption(item)}>
     <span>{formatTime(item.start)}</span>{(draftTexts[captionKey(item)]??item.text)||'빈 자막'}
    </button>)}
   </div>
   <div className="caption-edit">
    {framePreview}
    <label>자막 내용<textarea aria-label="자막 내용" maxLength={10000} value={draft.text} disabled={disabled}
     onChange={e=>{const text=e.target.value;setDraftTexts(previous=>({...previous,[key]:text}));}}/></label>
    <div className="button-row">
     <button className="secondary" disabled={disabled||!dirty} onClick={save}>자막 수정 저장</button>
     {dirty&&<span className="small muted">저장하지 않은 수정</span>}
    </div>
   </div>
  </div>:<p className="inline-empty">{clip.analyzed?'인식된 음성이 없습니다.':'자막을 생성하면 이곳에서 자막 줄을 선택하고 수정할 수 있습니다.'}</p>}
 </section>;

 return <div className="sequence-workspace" role="region" aria-label="여러 원본 편집">
  <nav ref={stepBar} className="sequence-steps" aria-label="여러 영상 작업 단계">
   {steps.map(([id,label],index)=><button type="button" key={id} aria-label={label+' 단계'}
    aria-current={step===id?'step':undefined} disabled={disabled} onClick={()=>goTo(id)}>
    <span aria-hidden="true">{index+1}</span>{label}
   </button>)}
  </nav>
  {progress&&<div className="panel sequence-progress" role="status"><p>{progress.message}</p><progress max={100} value={progress.percent}/></div>}

  {step==='captions'&&<>
   <section className="panel sequence-stage">
    <div className="section-title"><h2>포함한 영상의 자막 생성</h2></div>
    <div className="sequence-body">
     <p className="sequence-status">포함된 영상 {readyCount}/{included.length}개 자막 처리 완료</p>
     {pending.length>0&&<p className="small muted">아직 처리하지 않은 영상 {pending.length}개의 음성을 인식합니다. 만든 자막은 아래에서 확인하고 수정할 수 있습니다.</p>}
     {requiresModel&&<p className="small muted">음성이 있는 영상의 자막을 만들려면 한국어 음성 모델을 먼저 설치해 주세요.</p>}
     <div className="button-row sequence-actions">
      {requiresModel&&<button className="secondary" disabled={disabled} onClick={showModels}>모델 설정 열기</button>}
      {pending.length>0&&<button className="primary" disabled={disabled||requiresModel} onClick={analyzeAll}>포함된 영상 자막 만들기</button>}
      <button className={pending.length?'secondary':'primary'} disabled={disabled} onClick={()=>goTo('edit')}>
       {pending.length?'편집으로 이동 · 자막은 나중에':'영상 편집으로'}
      </button>
     </div>
    </div>
   </section>
   {captions}
  </>}

  <SequenceOutline active={step==='edit'} applied={hasOutline} revision={project.revision} disabled={disabled}
   duration={duration} formatTime={formatTime} load={loadOutline} preview={previewOutline} apply={applyOutline} clear={clearOutline}/>

  {step==='edit'&&<SequenceCuts clips={included} revision={project.revision} duration={hasOutline?null:duration}
   disabled={disabled} modelReady={modelReady} showModels={showModels} formatTime={formatTime}
   analyze={analyzeEdits} preview={previewCut} adjust={adjustCut} setCut={setCut}/>}

  {(step==='import'||step==='edit')&&<>
   <section className="panel sequence-panel">
    <div className="section-title"><h2>{step==='import'?'불러온 영상':'영상 편집 · 클립 순서'}</h2>
     {step==='import'&&<button className="secondary" disabled={disabled} onClick={replace}>새 영상 불러오기</button>}
    </div>
    <div className="sequence-body">
     <div className="sequence-summary">
      <span>{included.length}/{clips.length}개 포함 · {project.sortOrder==='capture'?'촬영 시간순':project.sortOrder==='import'?'불러온 순서':'편집 순서'}</span>
      <strong>예상 길이 {formatTime(duration)}</strong>
     </div>
     {hasOutline&&<p className="small muted">최종 순서와 포함 여부는 확정한 롱폼 구성에서 변경할 수 있습니다.</p>}
     <ol className="sequence-list">
      {clips.map((item,index)=><li key={item.id} data-clip={item.name} className={selected===item.id?'selected':''}
        draggable={!disabled&&!hasOutline} onDragStart={e=>e.dataTransfer.setData('application/x-localcut-clip',item.id)}
        onDragOver={e=>{if(!disabled&&!hasOutline&&e.dataTransfer.types.includes('application/x-localcut-clip'))e.preventDefault();}}
        onDrop={e=>{
         const dragged=e.dataTransfer.getData('application/x-localcut-clip');
         if(!dragged)return;
         e.preventDefault();
         move(clips.findIndex(c=>c.id===dragged),index);
        }}>
       <label className="checkbox"><input type="checkbox" aria-label={item.name+' 포함'} checked={item.enabled}
        disabled={disabled||hasOutline||(item.enabled&&included.length===1)}
        onChange={()=>order(clips.map(c=>c.id===item.id?{...c,enabled:!c.enabled}:c))}/></label>
       <button className="sequence-name quiet" disabled={disabled} onClick={()=>step==='edit'?open(item):selectClip(item.id)}><strong>{item.name}</strong><small>{formatTime(item.source.duration)}</small></button>
       <div className="sequence-move">
        <button className="quiet" disabled={disabled||hasOutline||index===0} onClick={()=>move(index,index-1)} aria-label={item.name+' 위로'}>↑</button>
        <button className="quiet" disabled={disabled||hasOutline||index===clips.length-1} onClick={()=>move(index,index+1)} aria-label={item.name+' 아래로'}>↓</button>
       </div>
      </li>)}
     </ol>
     {step==='edit'&&<div className="sequence-preview">
      <div className="button-row">
       <button className="secondary" disabled={disabled} onClick={()=>open(clip)}>선택한 원본 보기</button>
       {next&&!hasOutline&&<button className="secondary" disabled={disabled} onClick={openConnection}>다음 클립 연결부 보기</button>}
       <button className="secondary" disabled={disabled} onClick={()=>captionPanel.current?.scrollIntoView({block:"nearest"})}>자막 편집</button>
      </div>
      {previewUrl&&<video ref={sourcePlayer} key={previewUrl} src={previewUrl} controls preload="metadata" aria-label="선택한 원본 미리보기"/>}
      {connectionData&&connectionUrl&&<>
       <p className="small muted">{connectionData.from} → {connectionData.to} · {formatTime(connectionData.joinAt)}에서 연결</p>
       <video key={connectionUrl} src={connectionUrl} controls autoPlay aria-label="클립 연결부 미리보기"/>
      </>}
     </div>}
     <div className="button-row sequence-actions">
      {step==='edit'&&<button className="quiet" disabled={disabled||project.revision===0} onClick={undo}>이전 변경 되돌리기</button>}
      <button className="primary" disabled={disabled} onClick={()=>goTo(step==='import'?'captions':'settings')}>
       {step==='import'?'자막 생성으로':'설정 확인으로'}
      </button>
     </div>
    </div>
   </section>
   {step==='edit'&&captions}
  </>}

  {step==='settings'&&<section className="panel sequence-stage">
   <div className="section-title"><h2>자막 스타일과 출력 설정</h2></div>
   <div className="sequence-body">
    <div className="sequence-settings-layout">
     <div>
      <BasicSubtitleControls settings={project.settings} disabled={disabled} onChange={changeSettings}/>
      <SubtitleControls settings={project.settings} disabled={disabled} aspect="16:9" allowAspectChange={false} onChange={changeSettings}/>
     </div>
     <div className="sequence-settings-preview">
      {clipPicker}
      {framePreview||<p className="inline-empty">미리 볼 자막이 있는 클립을 선택하세요.</p>}
      {draft&&clip.captions.length>1&&<label>미리 볼 자막<select value={draft.id} disabled={disabled} onChange={e=>setCaptionId(e.target.value)}>
       {clip.captions.map(item=><option key={item.id} value={item.id}>{formatTime(item.start)} · {item.text}</option>)}
      </select></label>}
     </div>
    </div>
    <div className="sequence-output">
     <label>가로 출력 해상도<select aria-label="가로 출력 해상도" value={project.settings.resolution} disabled={disabled}
      onChange={e=>changeSettings({resolution:e.target.value as Settings['resolution']})}>
      <option value="1080">1080p</option><option value="720">720p</option>
     </select></label>
     <label className="checkbox"><input type="checkbox" disabled={disabled} checked={project.settings.subtitles}
      onChange={e=>changeSettings({subtitles:e.target.checked})}/> MP4에 자막 넣기</label>
    </div>
    <div className="sequence-audio-option">
     <label className="checkbox"><input type="checkbox" disabled={disabled} checked={project.settings.normalize}
      onChange={e=>changeSettings({normalize:e.target.checked})}/> 클립 간 음량 맞추기</label>
     <p className="small muted">편집 후 남은 오디오의 음량 차이를 측정해 최종 MP4와 출력 미리보기에 반영합니다.</p>
    </div>
    <div className="button-row sequence-actions">
     <button className="primary" disabled={disabled} onClick={()=>goTo('save')}>MP4 저장으로</button>
    </div>
   </div>
  </section>}

  {step==='save'&&<>
   <section className="panel sequence-stage">
    <div className="section-title" id={project.autoLongform?'auto-review':undefined}><h2>{project.autoLongform?'초안 검토하기':'최종 영상 저장'}</h2></div>
    <div className="sequence-body">
     <p className="sequence-status">{hasOutline?'확정한 롱폼 구성':`${included.length}개 영상`} · {formatTime(duration)} · {project.settings.resolution}p · {project.settings.subtitles?'자막 포함 설정':'자막 없이 저장'}</p>
     {project.settings.subtitles&&pending.length>0&&<div className="sequence-reminder">
      <span>자막을 만들지 않은 영상 {pending.length}개는 자막 없이 합쳐집니다.</span>
      <button className="secondary" disabled={disabled} onClick={()=>goTo('captions')}>자막 생성으로 돌아가기</button>
     </div>}
     {(project.settings.subtitles||project.autoLongform)&&unsavedCount>0&&<div className="sequence-reminder">
      <span>수정한 자막 {unsavedCount}줄이 아직 저장되지 않았습니다.</span>
      <button className="secondary" disabled={disabled} onClick={()=>goTo('captions')}>자막 편집으로 돌아가기</button>
     </div>}
     <div className="button-row sequence-actions">
      {project.autoLongform&&<>
       <button className="secondary" disabled={disabled} onClick={()=>goTo('captions')}>대본·자막 수정</button>
       <button className="secondary" disabled={disabled} onClick={()=>goTo('edit')}>컷·순서 수정</button>
      </>}
      {hasCurrentOutput&&<button className="quiet" disabled={disabled} onClick={saveSubtitles}>SRT 저장</button>}
      <button className="secondary" disabled={disabled} onClick={render}>{hasCurrentOutput?'미리보기 다시 만들기':'출력 미리보기 만들기'}</button>
     </div>
    </div>
   </section>
   {result(!!project.autoLongform&&unsavedCount>0)}
  </>}
 </div>;
}
