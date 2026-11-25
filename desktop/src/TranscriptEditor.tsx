import React, {useEffect, useMemo, useState} from 'react';
import type {Caption, Cut, Project, TranscriptOperation} from './types';

interface Props {
 project:Project;
 disabled:boolean;
 duration:number;
 formatTime:(seconds:number)=>string;
 seek:(seconds:number)=>void;
 edit:(operation:TranscriptOperation, ids:string[])=>Promise<void>;
 preview:(cutId:string)=>void;
}

type RemovedRange = Pick<Cut,'id'|'start'|'end'>;

function removedRanges(cuts:Cut[]):RemovedRange[] {
 const ranges:RemovedRange[]=[];
 for(const {id,start,end} of cuts.filter(c=>c.enabled).sort((a,b)=>a.start-b.start)){
  const previous=ranges.at(-1);
  if(previous&&start<=previous.end+1e-6)previous.end=Math.max(previous.end,end);
  else ranges.push({id,start,end});
 }
 return ranges;
}

function coverage(line:Caption,ranges:RemovedRange[],sourceDuration:number){
 let low=0,high=ranges.length;
 while(low<high){
  const middle=Math.floor((low+high)/2);
  if(ranges[middle].end<=line.start)low=middle+1;
  else high=middle;
 }
 let removed=0,cutId:string|undefined;
 for(let i=low;i<ranges.length&&ranges[i].start<line.end;i++){
  const {id,start,end}=ranges[i];
  removed+=Math.min(line.end,end)-Math.max(line.start,start);
  if(!cutId&&start>0&&end<sourceDuration)cutId=id;
 }
 return {removed,cutId,full:removed>=line.end-line.start-1e-6};
}

export function TranscriptEditor({project,disabled,duration,formatTime,seek,edit,preview}:Props){
 const [selected,setSelected]=useState<Set<string>>(new Set());
 const {captions,transcript,cuts}=project;
 useEffect(()=>setSelected(new Set()),[project.revision]);
 const ranges=useMemo(()=>removedRanges(cuts),[cuts]);
 const rows=useMemo(()=>(captions.length?captions:transcript).slice().sort((a,b)=>a.start-b.start)
  .map(line=>({line,...coverage(line,ranges,project.source.duration)})),[captions,transcript,ranges,project.source.duration]);
 const chosen=rows.filter(({line})=>selected.has(line.id));
 const canExclude=chosen.some(row=>!row.full);
 const canRestore=chosen.some(row=>row.removed>0);
 const selectedIds=()=>chosen.map(({line})=>line.id);

 return <section className="transcript-editor" aria-label="대본에서 영상 편집">
  <div className="transcript-edit-actions">
   <div><strong>{selected.size}줄 선택</strong><span>예상 결과 길이 <b>{formatTime(duration)}</b></span></div>
   <div className="button-row">
    <button className="quiet" disabled={disabled||!selected.size} onClick={()=>setSelected(new Set())}>선택 해제</button>
    <button className="secondary" disabled={disabled||!canRestore} onClick={()=>edit('restore',selectedIds())}>선택 구간 복원</button>
    <button className="primary small-button" disabled={disabled||!canExclude} onClick={()=>edit('exclude',selectedIds())}>선택 구간 제외</button>
   </div>
  </div>
  {rows.length>0?<><p className="small muted">대본 줄을 선택해 해당 영상 구간을 편집합니다. 문구를 고치려면 자막 수정 탭을 사용하세요.</p>
   <ul className="transcript-edit-list">
    {rows.map(({line,removed,full,cutId})=><li className={selected.has(line.id)?'selected':''} key={line.id}>
     <label className="checkbox">
      <input type="checkbox" disabled={disabled} checked={selected.has(line.id)} onChange={event=>{
       const checked=event.target.checked;
       setSelected(previous=>{
        const next=new Set(previous);
        if(checked)next.add(line.id);
        else next.delete(line.id);
        return next;
       });
      }}/>
      <span>{line.text||'빈 자막'}</span>
     </label>
     <span className={'status-pill '+(removed>0?'warning':'')}>{full?'제외됨':removed>0?'일부 제외':'보존'}</span>
     {cutId&&<button className="quiet" disabled={disabled} onClick={()=>preview(cutId)} aria-label={formatTime(line.start)+' 컷 연결부 보기'}>연결부 보기</button>}
     <button className="time-link" disabled={disabled} onClick={()=>seek(line.start)} aria-label={formatTime(line.start)+' 원본으로 이동'}>
      {formatTime(line.start)}<small>{formatTime(line.end)}</small>
     </button>
    </li>)}
   </ul>
  </>:<p className="inline-empty">음성 분석을 완료하면 편집할 대본이 표시됩니다.</p>}
 </section>;
}
