import React,{useEffect,useState} from 'react';
import type {Caption,Clip,ClipSelection,Progress,Project,SequenceConnection,Settings} from './types';

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
 saveCaption:(clipId:string,caption:Caption)=>Promise<boolean>;
 setting:<K extends keyof Settings>(key:K,value:Settings[K])=>Promise<void>;
 render:()=>void;
 undo:()=>void;
 replace:()=>void;
 saveSubtitles:()=>void;
}

export function SequenceEditor({project,disabled,progress,duration,formatTime,edit,preview,connection,
 analyze,saveCaption,setting,render,undo,replace,saveSubtitles}:Props) {
 const clips=project.clips!;
 const [selected,setSelected]=useState(clips[0].id);
 const [previewUrl,setPreviewUrl]=useState('');
 const [connectionData,setConnectionData]=useState<SequenceConnection|null>(null);
 const [connectionUrl,setConnectionUrl]=useState('');
 const [draft,setDraft]=useState<Caption|null>(null);
 const clip=clips.find(item=>item.id===selected)!;
 const included=clips.filter(item=>item.enabled);
 const position=included.findIndex(item=>item.id===selected);
 const next=position>=0?included[position+1]:undefined;

 useEffect(()=>{setConnectionData(null);},[project.revision]);
 useEffect(()=>{
  if(!connectionData){setConnectionUrl('');return;}
  const bytes=Uint8Array.from(atob(connectionData.video),c=>c.charCodeAt(0));
  const url=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
  setConnectionUrl(url);
  return ()=>URL.revokeObjectURL(url);
 },[connectionData]);

 function order(rows:Clip[]) {
  return edit(rows.map(({id,enabled})=>({id,enabled})));
 }
 function move(from:number,to:number) {
  if(disabled||from===to||from<0||to<0||to>=clips.length)return;
  const rows=clips.slice();
  const [item]=rows.splice(from,1);
  rows.splice(to,0,item);
  void order(rows);
 }
 async function open(item:Clip) {
  setSelected(item.id);setDraft(null);setConnectionData(null);setPreviewUrl('');
  setPreviewUrl((await preview(item.id))||'');
 }
 async function openConnection(){
  setPreviewUrl('');
  setConnectionData(await connection(clip.id));
 }
 async function save(){
  if(!draft)return;
  if(await saveCaption(clip.id,draft))setDraft(null);
 }

 return <section className="panel sequence-panel" aria-label="여러 원본 편집">
  <div className="section-title"><h2>클립 순서</h2><button className="quiet" disabled={disabled} onClick={replace}>새 영상 불러오기</button></div>
  <div className="sequence-body">
   <div className="sequence-summary"><span>{included.length}/{clips.length}개 포함 · {project.sortOrder==='capture'?'촬영 시간순':project.sortOrder==='import'?'불러온 순서':'편집 순서'}</span>
    <strong>예상 길이 {formatTime(duration)}</strong></div>
   <ol className="sequence-list">
    {clips.map((item,index)=><li key={item.id} data-clip={item.name} className={selected===item.id?'selected':''}
      draggable={!disabled} onDragStart={e=>e.dataTransfer.setData('application/x-localcut-clip',item.id)}
      onDragOver={e=>{if(!disabled&&e.dataTransfer.types.includes('application/x-localcut-clip'))e.preventDefault();}}
      onDrop={e=>{
       const dragged=e.dataTransfer.getData('application/x-localcut-clip');
       if(!dragged)return;
       e.preventDefault();
       move(clips.findIndex(c=>c.id===dragged),index);
      }}>
     <label className="checkbox"><input type="checkbox" aria-label={item.name+' 포함'} checked={item.enabled}
      disabled={disabled||(item.enabled&&included.length===1)}
      onChange={()=>order(clips.map(c=>c.id===item.id?{...c,enabled:!c.enabled}:c))}/></label>
     <button className="sequence-name quiet" disabled={disabled} onClick={()=>open(item)}><strong>{item.name}</strong><small>{formatTime(item.source.duration)}</small></button>
     <div className="sequence-move">
      <button className="quiet" disabled={disabled||index===0} onClick={()=>move(index,index-1)} aria-label={item.name+' 위로'}>↑</button>
      <button className="quiet" disabled={disabled||index===clips.length-1} onClick={()=>move(index,index+1)} aria-label={item.name+' 아래로'}>↓</button>
     </div>
    </li>)}
   </ol>
   {progress&&<div className="sequence-progress" role="status"><p>{progress.message}</p><progress max={100} value={progress.percent}/></div>}
   <div className="sequence-preview">
    <div className="button-row">
     <button className="secondary" disabled={disabled} onClick={()=>open(clip)}>선택한 원본 보기</button>
     {next&&<button className="secondary" disabled={disabled} onClick={openConnection}>다음 클립 연결부 보기</button>}
    </div>
    {previewUrl&&<video key={previewUrl} src={previewUrl} controls preload="metadata" aria-label="선택한 원본 미리보기"/>}
    {connectionData&&connectionUrl&&<>
     <p className="small muted">{connectionData.from} → {connectionData.to} · {formatTime(connectionData.joinAt)}에서 연결</p>
     <video key={connectionUrl} src={connectionUrl} controls autoPlay aria-label="클립 연결부 미리보기"/>
    </>}
   </div>
   <div className="sequence-captions">
    <div className="button-row">
     <h3>선택한 클립 자막</h3>
     {!clip.analyzed&&<button className="secondary" disabled={disabled} onClick={()=>analyze(clip.id)}>클립 자막 만들기</button>}
    </div>
    {!!clip.captions.length&&<label>수정할 자막 줄<select value={draft?.id||''} disabled={disabled} onChange={e=>{
     const cue=clip.captions.find(c=>c.id===e.target.value);setDraft(cue?{...cue}:null);
    }}><option value="">자막 선택</option>{clip.captions.map(c=><option key={c.id} value={c.id}>{formatTime(c.start)} · {c.text}</option>)}</select></label>}
    {draft&&<div className="sequence-caption-editor"><label>자막 내용<textarea maxLength={10000} value={draft.text} disabled={disabled}
     onChange={e=>setDraft({...draft,text:e.target.value})}/></label>
     <button className="secondary" disabled={disabled} onClick={save}>자막 수정 저장</button></div>}
    {clip.analyzed&&!clip.captions.length&&<p className="small muted">인식된 음성이 없습니다.</p>}
   </div>
   <div className="sequence-output">
    <label>가로 출력 해상도<select aria-label="가로 출력 해상도" value={project.settings.resolution} disabled={disabled} onChange={e=>setting('resolution',e.target.value as Settings['resolution'])}>
     <option value="1080">1080p</option><option value="720">720p</option></select></label>
    <label className="checkbox"><input type="checkbox" disabled={disabled} checked={project.settings.subtitles} onChange={e=>setting('subtitles',e.target.checked)}/> MP4에 자막 넣기</label>
   </div>
   <div className="button-row sequence-actions">
    <button className="quiet" disabled={disabled||project.revision===0} onClick={undo}>이전 변경 되돌리기</button>
    {project.output?.revision===project.revision&&<button className="quiet" disabled={disabled} onClick={saveSubtitles}>SRT 저장</button>}
    {project.output?.revision===project.revision&&<button className="secondary" disabled={disabled} onClick={render}>MP4 다시 출력</button>}
    {project.output?.revision!==project.revision&&<button className="primary" disabled={disabled} onClick={render}>MP4 출력</button>}
   </div>
  </div>
 </section>;
}
