import {useEffect,useState} from 'react';
import type {Clip,SequenceCutPreview} from './types';

interface Props {
 clips:Clip[];
 revision:number;
 duration:number;
 disabled:boolean;
 modelReady:boolean;
 showModels:()=>void;
 formatTime:(seconds:number)=>string;
 analyze:()=>Promise<void>;
 preview:(clipId:string,cutId:string)=>Promise<SequenceCutPreview|null>;
 setCut:(clipId:string,cutId:string,enabled:boolean)=>Promise<void>;
}

const cutLabels:Record<string,string>={
 silence:'긴 침묵',speech_gap:'대화 공백',retake:'반복 발화',mistake:'다시 말하기'
};

export function SequenceCuts({clips,revision,duration,disabled,modelReady,showModels,formatTime,analyze,preview,setCut}:Props){
 const [selected,setSelected]=useState('');
 const [previewData,setPreviewData]=useState<(SequenceCutPreview&{label:string})|null>(null);
 const [url,setUrl]=useState('');
 const reviewed=clips.flatMap(clip=>clip.cuts??[]);
 const applied=reviewed.filter(cut=>cut.enabled).length;
 const pending=clips.filter(clip=>!clip.cuts);
 const requiresModel=!modelReady&&pending.some(clip=>clip.source.hasAudio&&!clip.speechReady);
 const clip=clips.find(item=>item.id===selected)??clips.find(item=>item.cuts?.length)??clips[0];
 const original=clips.reduce((seconds,item)=>seconds+Math.max(1,Math.round(item.source.duration*30))/30,0);
 const savedTime=Math.max(0,original-duration);

 useEffect(()=>{setPreviewData(null);},[revision]);
 useEffect(()=>{
  if(!previewData){setUrl('');return;}
  const bytes=Uint8Array.from(atob(previewData.video),character=>character.charCodeAt(0));
  const objectUrl=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
  setUrl(objectUrl);
  return ()=>URL.revokeObjectURL(objectUrl);
 },[previewData]);

 async function openPreview(cutId:string,label:string){
  setPreviewData(null);
  const result=await preview(clip.id,cutId);
  if(result)setPreviewData({...result,label});
 }

 return <section className="panel sequence-ai-cuts" aria-label="클립 안에서 AI 편집">
  <div className="section-title">
   <h2>클립 안에서 AI 편집</h2>
   {pending.length>0&&<button className="primary" disabled={disabled||requiresModel} onClick={analyze}>AI 편집점 찾기</button>}
  </div>
  <div className="sequence-body">
   {pending.length>0&&<p className="small muted">포함된 영상 {pending.length}개를 분석합니다. 근거가 충분한 긴 침묵은 자동으로 줄이고, 반복 발화와 애매한 구간은 검토할 수 있습니다.</p>}
   {requiresModel&&<div className="sequence-reminder">
    <span>음성 분석을 시작하려면 한국어 음성 모델을 준비해 주세요.</span>
    <button className="secondary" disabled={disabled} onClick={showModels}>모델 설정 열기</button>
   </div>}
   {pending.length<clips.length&&<>
    <p className="sequence-status">분석 {clips.length-pending.length}/{clips.length}개 · 컷 적용 {applied}개 · 검토 {reviewed.length-applied}개</p>
    <p className="small muted">원본 {formatTime(original)} → 예상 {formatTime(duration)}{savedTime>.01&&` · ${formatTime(savedTime)} 단축`}</p>
    <label>편집 구간을 볼 클립<select aria-label="편집 구간을 볼 클립" value={clip.id} disabled={disabled}
     onChange={event=>{setSelected(event.target.value);setPreviewData(null);}}>
     {clips.map(item=><option key={item.id} value={item.id}>{item.name} · {item.cuts?`후보 ${item.cuts.length}개`:'분석 전'}</option>)}
    </select></label>
    {clip.cuts?.length?<ul className="sequence-cut-list">
     {clip.cuts.map(cut=>{
      const range=`${formatTime(cut.start)}–${formatTime(cut.end)}`;
      return <li key={cut.id}>
       <label className="checkbox">
        <input type="checkbox" aria-label={`컷 적용 ${range}`} checked={cut.enabled} disabled={disabled}
         onChange={event=>setCut(clip.id,cut.id,event.target.checked)}/>
        <span><strong>{range} · {cutLabels[cut.kind]??'편집 구간'}</strong><small>{cut.reason}</small></span>
       </label>
       <button className="secondary" disabled={disabled} onClick={()=>openPreview(cut.id,range)}>컷 미리보기</button>
      </li>;
     })}
    </ul>:<p className="small muted">{clip.cutNote??'이 클립의 편집점 분석을 진행해 주세요.'}</p>}
    {previewData&&url&&<div className="cut-connection-preview">
     <h3>{previewData.label} 삭제 미리보기</h3>
     <p>컷 위치 {formatTime(previewData.joinAt)}</p>
     <video key={url} src={url} controls autoPlay aria-label="클립 내부 컷 미리보기"/>
    </div>}
   </>}
  </div>
 </section>;
}
