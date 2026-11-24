import {useEffect,useState,type RefObject} from 'react';

export function PreviewSeekControls({videoRef,mediaKey,label,onSeek}:{videoRef:RefObject<HTMLVideoElement|null>;mediaKey:string;label:string;onSeek?:(time:number)=>void}){
 const [ready,setReady]=useState(false);
 useEffect(()=>{
  const video=videoRef.current;
  if(!video){setReady(false);return;}
  const refresh=()=>setReady(video.readyState>=1&&!video.error&&Number.isFinite(video.duration)&&video.duration>0);
  const events=['loadedmetadata','durationchange','emptied','error'];
  events.forEach(event=>video.addEventListener(event,refresh));refresh();
  return ()=>events.forEach(event=>video.removeEventListener(event,refresh));
 },[videoRef,mediaKey]);
 function move(seconds:number){
  const video=videoRef.current;
  if(!video||video.readyState<1||video.error||!Number.isFinite(video.duration)||video.duration<=0)return;
  const next=Math.max(0,Math.min(video.duration,video.currentTime+seconds));
  video.currentTime=next;
  onSeek?.(next);
 }
 return <div className="preview-seek-controls" role="group" aria-label={`${label} 탐색`}>
  <button className="secondary" type="button" disabled={!ready} aria-label={`${label} 5초 뒤로`} onClick={()=>move(-5)}><span aria-hidden="true">↶</span>5초 뒤로</button>
  <button className="secondary" type="button" disabled={!ready} aria-label={`${label} 5초 앞으로`} onClick={()=>move(5)}>5초 앞으로<span aria-hidden="true">↷</span></button>
 </div>;
}
