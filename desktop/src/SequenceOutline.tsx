import {useEffect,useRef,useState} from 'react';
import type {ClipSelection,OutlineRow,SequenceOutlineDraft,SequenceOutlinePreview} from './types';

interface Props {
 active:boolean;
 applied:boolean;
 revision:number;
 disabled:boolean;
 duration:number;
 formatTime:(seconds:number)=>string;
 load:(fresh:boolean)=>Promise<SequenceOutlineDraft|null>;
 preview:(rowId:string,fresh:boolean)=>Promise<SequenceOutlinePreview|null>;
 apply:(rows:ClipSelection[],fresh:boolean)=>Promise<boolean>;
 clear:()=>Promise<boolean>;
}

export function SequenceOutline({active,applied,revision,disabled,duration,formatTime,load,preview,apply,clear}:Props){
 const [draft,setDraft]=useState<SequenceOutlineDraft|null>(null);
 const [fresh,setFresh]=useState(false);
 const [media,setMedia]=useState<(SequenceOutlinePreview&{name:string})|null>(null);
 const [url,setUrl]=useState('');
 const previewPanel=useRef<HTMLDivElement>(null);
 const available=draft?.rows.filter(row=>row.enabled&&row.seconds>0)??[];
 const length=available.reduce((seconds,row)=>seconds+row.seconds,0);
 const stale=!!draft&&draft.revision!==revision;

 useEffect(()=>{setMedia(null);},[revision,active]);
 useEffect(()=>{
  if(!media){setUrl('');return;}
  const bytes=Uint8Array.from(atob(media.video),character=>character.charCodeAt(0));
  const objectUrl=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
  setUrl(objectUrl);
  return ()=>URL.revokeObjectURL(objectUrl);
 },[media]);
 useEffect(()=>{
  if(url)previewPanel.current?.scrollIntoView({block:'nearest'});
 },[url]);

 async function open(newDraft:boolean){
  const result=await load(newDraft);
  if(result){setDraft(result);setFresh(newDraft);setMedia(null);}
 }
 function move(index:number,offset:number){
  if(!draft)return;
  const rows=draft.rows.slice();
  const [row]=rows.splice(index,1);
  rows.splice(index+offset,0,row);
  setDraft({...draft,rows});
 }
 async function openPreview(row:OutlineRow){
  setMedia(null);
  const result=await preview(row.id,fresh);
  if(result)setMedia({...result,name:row.name});
 }
 async function confirm(){
  if(!draft||!available.length||stale)return;
  if(await apply(draft.rows.map(({id,enabled})=>({id,enabled})),fresh)){
   setDraft(null);setMedia(null);
  }
 }

 return <section hidden={!active} className="panel sequence-outline" aria-label="여러 영상 롱폼 구성">
  <div className="section-title">
   <h2>유튜브 롱폼 구성</h2>
   {!draft&&<button className="primary" disabled={disabled} onClick={()=>open(!applied)}>
    {applied?'확정 구성 다시 열기':'롱폼 구성 초안 만들기'}
   </button>}
  </div>
  <div className="sequence-body">
   {applied&&<p className="sequence-status">롱폼 구성 적용 중 · {formatTime(duration)}</p>}
   {!draft&&!applied&&<p className="small muted">저장한 자막의 전환 표현과 클립 경계를 참고해 도입·본론·마무리를 제안합니다.</p>}
   {draft&&<>
    <p className="sequence-status">포함할 구간 {available.length}/{draft.rows.length}개 · 예상 {formatTime(length)}</p>
    {!draft.hasCaptions&&<p className="small muted">저장된 자막이 없어 현재 클립의 경계를 기준으로 구성했습니다.</p>}
    <p className="small muted">위에서 아래 순서로 연결됩니다. 확인한 구간을 포함하고 구성을 확정하세요.</p>
    {stale&&<p className="sequence-reminder" role="status">편집 내용이 바뀌었습니다. 현재 상태에서 초안을 다시 열어 주세요.</p>}
    <ol className="sequence-cut-list outline-list">
     {draft.rows.map((row,index)=><li key={row.id}>
      <label className="checkbox">
       <input type="checkbox" aria-label={`구간 ${index+1} 포함`} checked={row.enabled&&row.seconds>0}
        disabled={disabled||stale||row.seconds===0}
        onChange={event=>setDraft({...draft,rows:draft.rows.map(item=>item.id===row.id?{...item,enabled:event.target.checked}:item)})}/>
       <span>
        <strong>{row.role} · {row.name}</strong>
        <small>원본 {formatTime(row.startFrame/30)}–{formatTime(row.endFrame/30)} · {formatTime(row.seconds)} · {row.reason}</small>
        {row.excerpt&&<small>{row.excerpt}</small>}
       </span>
      </label>
      <div className="button-row outline-row-actions">
       <button className="secondary" disabled={disabled||stale||!row.seconds} onClick={()=>openPreview(row)}>구간 미리보기</button>
       <button className="quiet" aria-label={`구간 ${index+1} 위로`} disabled={disabled||stale||index===0} onClick={()=>move(index,-1)}>↑</button>
       <button className="quiet" aria-label={`구간 ${index+1} 아래로`} disabled={disabled||stale||index===draft.rows.length-1} onClick={()=>move(index,1)}>↓</button>
      </div>
     </li>)}
    </ol>
    {media&&url&&<div className="cut-connection-preview" ref={previewPanel}>
     <h3>{media.name} · {formatTime(media.seconds)} 미리보기</h3>
     <video src={url} key={url} controls autoPlay aria-label="롱폼 구성 구간 미리보기"/>
    </div>}
    <div className="button-row sequence-actions">
     <button className="quiet" disabled={disabled} onClick={()=>{setDraft(null);setMedia(null);}}>검토 닫기</button>
     {(stale||applied)&&<button className="secondary" disabled={disabled}
      onClick={()=>open(stale?fresh:true)}>{stale?'현재 구성 다시 열기':'교정 자막으로 새 초안'}</button>}
     <button className="primary" disabled={disabled||stale||!available.length} onClick={confirm}>롱폼 구성 확정</button>
    </div>
   </>}
   {applied&&!draft&&<div className="button-row sequence-actions">
    <button className="secondary" disabled={disabled} onClick={clear}>클립 순서로 돌아가기</button>
   </div>}
  </div>
 </section>;
}
