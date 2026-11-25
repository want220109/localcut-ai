import React, {useEffect, useRef, useState} from 'react';
import type {CutPreview} from './types';

interface Props {
 clip?:CutPreview;
 error?:string;
 formatTime:(seconds:number)=>string;
 close:()=>void;
}

export function CutConnectionPreview({clip,error,formatTime,close}:Props){
 const [url,setUrl]=useState('');
 const panel=useRef<HTMLElement>(null);
 useEffect(()=>{panel.current?.scrollIntoView({block:'nearest'});},[url,error]);
 useEffect(()=>{
  if(!clip)return;
  const bytes=Uint8Array.from(atob(clip.video),character=>character.charCodeAt(0));
  const local=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
  setUrl(local);
  return ()=>URL.revokeObjectURL(local);
 },[clip]);

 return <section ref={panel} className="cut-connection-preview" aria-label="컷 연결부 미리보기">
  <div><h3>컷 연결부 미리보기</h3><button className="quiet" onClick={close}>미리보기 닫기</button></div>
  {error?<p role="alert">{error}</p>:clip&&<>
   <p>원본 {formatTime(clip.cutStart)} – {formatTime(clip.cutEnd)} 컷 · 미리보기의 {formatTime(clip.joinAt)}에서 연결</p>
   {url&&<video src={url} controls autoPlay aria-label="컷 앞뒤 재생"/>}
  </>}
 </section>;
}
