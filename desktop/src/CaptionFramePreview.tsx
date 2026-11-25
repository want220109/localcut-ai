import {useEffect,useState} from 'react';
import type {Caption} from './types';

type Frame={image:string;sourceTime:number;message:string|null};

// Keep a single request running even when the user switches captions or tabs.
let inFlight:Promise<Frame>|null=null;

export function CaptionFramePreview({projectId,revision,clipId,caption,paused,formatTime}:{
 projectId:string;revision:number;clipId?:string;caption:Caption;paused:boolean;formatTime:(seconds:number)=>string;
}){
 const [frame,setFrame]=useState<Frame|null>(null);
 const [pending,setPending]=useState(true);
 const [error,setError]=useState('');

 useEffect(()=>{
  const bridge=window.localcut;
  if(paused||!bridge)return;
  let active=true;
  setPending(true);
  setError('');
  const timer=window.setTimeout(async()=>{
   while(inFlight){
    await inFlight.catch(()=>{});
    if(!active)return;
   }
   if(!active)return;
   const request=bridge.call('captionFrame',{
    id:projectId,revision,clipId,captionId:caption.id,text:caption.text,start:caption.start,end:caption.end
   }) as Promise<Frame>;
   inFlight=request;
   try{
    const result=await request;
    if(active)setFrame(result);
   }catch(error){
    if(active){
     setFrame(null);
     setError(String(error instanceof Error?error.message:error).replace(/^Error invoking remote method 'localcut': (?:Error: )?/,''));
    }
   }finally{
    if(inFlight===request)inFlight=null;
    if(active)setPending(false);
   }
  },350);
  return ()=>{active=false;window.clearTimeout(timer);};
 },[projectId,revision,clipId,caption,paused]);

 return <figure className="caption-frame" aria-label="자막 정지 화면 미리보기" aria-busy={pending||paused}>
  <figcaption><strong>자막 정지 화면</strong>{frame&&<span>원본 {formatTime(frame.sourceTime)}</span>}</figcaption>
  <div className="caption-frame-image">
   {frame&&<img src={frame.image} alt="현재 자막과 출력 설정을 적용한 정지 화면"/>}
   {!frame&&!error&&<span>장면을 불러오는 중…</span>}
  </div>
  <div className="caption-frame-status" role={error?'alert':'status'}>
   {error||(paused?'작업이 끝나면 갱신합니다.':pending?'장면 갱신 중…':frame?.message)}
  </div>
 </figure>;
}
