import React, {useEffect, useRef, useState} from 'react';
import type {LongformDraft, Project} from './types';

interface Props {
 project:Project;
 disabled:boolean;
 formatTime:(seconds:number)=>string;
 createDraft:(targetSeconds:number)=>Promise<LongformDraft|null>;
 applyDraft:(draft:LongformDraft, selected:string[])=>Promise<boolean>;
}

export function LongformEditor({project,disabled,formatTime,createDraft,applyDraft}:Props) {
 const duration=project.source.duration;
 const initial=Math.max(.001,Math.floor(duration*.8*10)/10);
 const [minutes,setMinutes]=useState(String(Math.floor(initial/60)));
 const [seconds,setSeconds]=useState(String(Math.round((initial%60)*1000)/1000));
 const [draft,setDraft]=useState<LongformDraft|null>(null);
 const [selected,setSelected]=useState<string[]>([]);
 const [applied,setApplied]=useState(0);
 const [preview,setPreview]=useState<{time:number;label:string}|null>(null);
 const player=useRef<HTMLVideoElement>(null);
 const target=Number(minutes)*60+Number(seconds);
 const valid=Number.isInteger(Number(minutes))&&Number(minutes)>=0&&Number(seconds)>=0&&Number(seconds)<60&&target>=.001&&target<=duration;
 const stale=!!draft&&(draft.revision!==project.revision||draft.targetSeconds!==target);
 const proposedLength=draft ? Math.max(0,draft.currentSeconds-draft.candidates.reduce(
  (removed,candidate)=>removed+(selected.includes(candidate.id)?candidate.end-candidate.start:0),0)) : 0;

 function seekPreview(){
  if(!preview||!player.current||player.current.readyState<1)return;
  player.current.pause();
  player.current.currentTime=preview.time;
 }

 useEffect(seekPreview,[preview]);
 useEffect(()=>{if(disabled)player.current?.pause();},[disabled]);

 async function generate(event:React.FormEvent){
  event.preventDefault();
  if(!valid||disabled)return;
  const result=await createDraft(target);
  if(!result)return;
  setDraft(result);
  setSelected(result.candidates.filter(c=>c.recommended).map(c=>c.id));
  setApplied(0);
  setPreview(null);
 }

 async function apply(){
  if(!draft||!selected.length||stale||disabled||proposedLength<=.001)return;
  if(!await applyDraft(draft,selected))return;
  setApplied(selected.length);
  setDraft(null);
  setSelected([]);
 }

 return <section className="longform-editor" aria-label="유튜브 롱폼 초벌 편집">
  <form className="longform-form" onSubmit={generate}>
   <fieldset disabled={disabled}>
    <legend>목표 영상 길이</legend>
    <label><input aria-label="목표 길이 (분)" type="number" min="0" step="1" value={minutes} onChange={e=>setMinutes(e.target.value)}/> 분</label>
    <label><input aria-label="목표 길이 (초)" type="number" min="0" max="59.999" step="any" value={seconds} onChange={e=>setSeconds(e.target.value)}/> 초</label>
   </fieldset>
   <button type="submit" className="primary small-button" disabled={!valid||disabled}>초벌 편집안 만들기</button>
  </form>
  <p className="small muted">{project.analyzed?'현재 저장한 자막과 컷을 기준으로 편집안을 만듭니다.':'원본을 분석해 자막과 편집안을 한 번에 만듭니다.'} 목표 시간은 편집 후보를 고르는 데 사용합니다.</p>
  {!valid&&<p className="longform-note">목표 길이를 원본 길이 {formatTime(duration)} 이내로 입력해 주세요.</p>}
  {!!applied&&!draft&&<p className="longform-note" role="status">{applied}개 컷을 적용했습니다. 편집 구간에서 수정하거나 MP4 출력을 눌러 결과를 재생할 수 있습니다.</p>}
  {draft&&<>
   {stale&&<p className="longform-note" role="status">편집 내용이나 목표 길이가 바뀌었습니다. 초벌 편집안을 다시 만들어 주세요.</p>}
   <div className="longform-overview">
    <div className="longform-sections">
     {draft.sections.map(section=><article key={section.title}>
      <div className="longform-section-title"><h3>{section.title}</h3><span>{formatTime(section.start)} – {formatTime(section.end)}</span></div>
      {section.excerpt&&<blockquote>{section.excerpt}</blockquote>}
      <p>{section.reason}{section.retainedSeconds<=.001?' 현재 편집에서 제외된 구간입니다.':''}</p>
      <button type="button" className="quiet" disabled={disabled} onClick={()=>setPreview({time:section.previewTime,label:section.title})}>{section.title} 원본 보기</button>
     </article>)}
    </div>
    <div className="longform-preview">
     <h3>원본 미리보기 {preview&&<small>{preview.label} · {formatTime(preview.time)}</small>}</h3>
     <video ref={player} src={project.sourceUrl} controls preload="metadata" onLoadedMetadata={seekPreview}/>
    </div>
   </div>
   <div className="longform-cuts">
    <div className="longform-cut-header">
     <h3>줄일 구간</h3>
     <p>현재 <strong>{formatTime(draft.currentSeconds)}</strong> · 선택 반영 후 <strong>{formatTime(proposedLength)}</strong> · 목표 <strong>{formatTime(draft.targetSeconds)}</strong></p>
    </div>
    {!draft.hasDialogue&&<p className="longform-note">대사 근거가 부족해 삭제를 제안하지 않았습니다. 장면을 확인한 뒤 편집 구간에서 직접 컷을 추가할 수 있습니다.</p>}
    {draft.hasDialogue&&!draft.candidates.length&&<p className="longform-note">현재 구성에서 핵심 대사를 보호하며 줄일 만한 구간을 찾지 못했습니다.</p>}
    {draft.candidates.length>0&&<>
     <p className="small muted">추천 후보를 먼저 선택했습니다. 원본을 확인하고 적용할 구간만 선택하세요.</p>
     <ul>
      {draft.candidates.map(candidate=><li key={candidate.id}>
       <label className="checkbox">
        <input type="checkbox" disabled={disabled||stale} checked={selected.includes(candidate.id)} onChange={event=>{
         const checked=event.target.checked;
         setSelected(values=>checked?[...values,candidate.id]:values.filter(id=>id!==candidate.id));
        }}/>
        <span>{formatTime(candidate.start)} – {formatTime(candidate.end)} · {candidate.reason}</span>
       </label>
       <button type="button" className="quiet" aria-label={formatTime(candidate.start)+' 컷 후보 원본 보기'} disabled={disabled} onClick={()=>setPreview({time:candidate.start,label:'컷 후보'})}>원본 보기</button>
      </li>)}
     </ul>
    </>}
    {proposedLength>draft.targetSeconds+.05&&<p className="longform-note">현재 선택으로는 목표보다 {formatTime(proposedLength-draft.targetSeconds)} 깁니다. 확인한 구간만 적용할 수 있습니다.</p>}
    <button type="button" className="secondary" disabled={disabled||stale||!selected.length||proposedLength<=.001} onClick={apply}>선택한 컷 적용 ({selected.length})</button>
   </div>
  </>}
 </section>;
}
