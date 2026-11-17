import React from 'react';
import catalog from '../../subtitles/presets.json';
import type {Settings} from './types';

export const subtitlePresetChanges=(id:string):Partial<Settings>=>{
 if(id==='legacy')return {...catalog.defaults,fontSize:48,color:'#FFFFFF',outline:2,background:false,position:'bottom'} as Partial<Settings>;
 const preset=catalog.presets.find(p=>p.id===id);
 return preset?{...preset.settings,subtitlePreset:id} as Partial<Settings>:{subtitlePreset:id};
};

export function SubtitleControls({settings,disabled,aspect,onChange}:{settings:Settings;disabled:boolean;aspect:string;onChange:(settings:Partial<Settings>)=>void}){
 const preset=catalog.presets.find(p=>p.id===settings.subtitlePreset);
 const font=catalog.fonts[settings.fontFamily||'malgun'];
 const terms=(settings.highlightWords||'').split(',').map(w=>w.trim()).filter(Boolean).sort((a,b)=>b.length-a.length);
 const sample='당신의 이야기가 더 선명해지는 순간';
 const pattern=terms.length?new RegExp('('+terms.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','g'):null;
 const parts=pattern?sample.split(pattern):[sample];
 const custom=(changes:Partial<Settings>)=>onChange({...changes,subtitlePreset:'custom'});
 return <div className="platform-subtitles">
  <label className="quality-label">업로드용 자막 프리셋<select aria-label="자막 프리셋" disabled={disabled} value={settings.subtitlePreset||'legacy'} onChange={e=>onChange(subtitlePresetChanges(e.target.value))}>
   <option value="legacy">기존 자막 스타일 유지</option><option value="custom">직접 설정</option>
   {catalog.presets.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}
  </select></label>
  {preset&&<p className="preset-description">{preset.description}<span>권장 비율 {preset.aspect} · 영상 비율은 직접 선택</span></p>}
  {preset&&aspect!==preset.aspect&&<button className="quiet preset-aspect" disabled={disabled} onClick={()=>onChange({aspect:preset.aspect as Settings['aspect']})}>{preset.aspect} 화면 비율 적용</button>}
  <div className="subtitle-sample platform-sample" aria-label="자막 스타일 예시" style={{fontFamily:`"${font.css}", "Malgun Gothic", sans-serif`,fontWeight:settings.fontBold?700:400,color:settings.color,background:settings.background?'#111820':undefined,textShadow:`${Math.min(3,settings.captionShadow||0)}px ${Math.min(3,settings.captionShadow||0)}px 2px #000`,WebkitTextStroke:settings.outline?'.35px #111':'0'}}>
   {parts.map((part,i)=><span key={i} style={pattern&&i%2?{color:settings.highlightColor}:undefined}>{part}</span>)}
  </div>
  <p className="sample-caption">폰트·색상 예시 · 실제 크기와 위치는 출력 영상에 반영됩니다.</p>
  <label className="quality-label">글꼴<select aria-label="자막 글꼴" disabled={disabled} value={settings.fontFamily||'malgun'} onChange={e=>custom({fontFamily:e.target.value as Settings['fontFamily']})}>{Object.entries(catalog.fonts).map(([id,f])=><option key={id} value={id}>{f.label}</option>)}</select></label>
  <div className="two-fields subtitle-detail"><label>글자 두께<select aria-label="자막 두께" disabled={disabled} value={settings.fontBold?'bold':'normal'} onChange={e=>custom({fontBold:e.target.value==='bold'})}><option value="normal">보통</option><option value="bold">굵게</option></select></label>
   <label>위치 여백<select aria-label="자막 위치 여백" disabled={disabled} value={settings.captionMarginVertical??7.5} onChange={e=>custom({captionMarginVertical:Number(e.target.value)})}>{[...new Set([5,7.5,8,15,20,23,24,25,30,35,settings.captionMarginVertical??7.5])].sort((a,b)=>a-b).map(n=><option key={n} value={n}>{n}%</option>)}</select></label></div>
  <label className="quality-label">강조 단어 <span className="optional-label">선택 · 쉼표로 구분</span><input key={settings.highlightWords} aria-label="강조 단어" disabled={disabled} defaultValue={settings.highlightWords||''} placeholder="예: 핵심, 추천, 오늘" maxLength={500} onBlur={e=>{if(e.target.value!==settings.highlightWords)custom({highlightWords:e.target.value});}}/></label>
  <div className="two-fields subtitle-detail"><label>강조 색상<input aria-label="강조 색상" type="color" disabled={disabled} value={settings.highlightColor||'#D6FF62'} onChange={e=>custom({highlightColor:e.target.value})}/></label>
   <label>크기 기준<select aria-label="자막 크기 기준" disabled={disabled} value={settings.captionScale||'height'} onChange={e=>custom({captionScale:e.target.value as Settings['captionScale']})}><option value="short-edge">짧은 변 1080px</option><option value="height">높이 1080px · 기존</option></select></label></div>
  <label className="checkbox"><input aria-label="두 줄 자동 배치" type="checkbox" disabled={disabled} checked={settings.captionWrap||false} onChange={e=>custom({captionWrap:e.target.checked})}/> 두 줄 이내로 자동 배치</label>
  <p className="preset-footnote">프리셋 변경은 대본·자막 문구·시간을 보존합니다. 변경 후 MP4를 다시 출력하세요. 플랫폼 표시 영역은 기기·화면에 따라 달라질 수 있습니다.</p>
 </div>;
}
