export interface Cut {id:string;start:number;end:number;kind:string;reason:string;confidence:number;enabled:boolean;review:boolean}
export interface Caption {id:string;start:number;end:number;text:string;textEdited?:boolean;words?:Word[]}
export interface Word {start:number;end:number;text:string;confidence:number}
export interface Segment extends Caption {confidence:number;important?:boolean;score?:number}
export interface Settings {
 subtitles:boolean;fontSize:number;color:string;outline:number;background:boolean;position:'bottom'|'middle'|'top';
 resolution:'source'|'720'|'1080';aspect:'source'|'16:9'|'9:16'|'1:1';quality:'high'|'balanced'|'small';zoom:number;denoise:boolean;normalize:boolean;
 subtitlePreset:string;fontFamily:'malgun'|'nanum'|'blackhan';fontBold:boolean;captionScale:'height'|'short-edge';
 captionSizeMode:'auto'|'manual';
 captionMarginVertical:number;captionMarginLeft:number|null;captionMarginRight:number|null;captionShadow:number;captionWrap:boolean;captionMaxChars:number;
 highlightWords:string;highlightColor:string;
}
export interface Clip {
 id:string;name:string;enabled:boolean;source:Project['source'];captions:Caption[];analyzed:boolean;speechReady?:boolean;cuts?:Cut[];cutNote?:string;
}
export interface ClipSelection {id:string;enabled:boolean}
export interface Project {
  id:string;name:string;style:'basic'|'fast'|'shorts';analyzed:boolean;revision:number;sourceUrl:string;outputUrl?:string;preview?:string|null;
  source:{path:string;duration:number;width:number;height:number;fps:number;aspect:string;hasAudio:boolean;bytes:number;capturedAt?:number|null};
  cuts:Cut[];captions:Caption[];transcript:Segment[];scenes:number[];warnings:string[];settings:Settings;
  model:{name:string;device:string}|null;output:{path:string;duration:number;revision:number}|null;
  clips?:Clip[];sortOrder?:'capture'|'import'|'manual';
}
export interface CutSummary {sourceDuration:number;outputDuration:number;removedDuration:number;appliedCount:number;reviewCount:number;intervalCount:number;noCutReason:string;analysisNeedsRefresh:boolean}
export interface Audit {before:string;after:string;removed:{id:string;text:string;important:boolean}[];partial:{id:string;text:string;retained:number}[];importantRemoved:number;outputDuration:number;cutSummary?:CutSummary}
export interface Model {id:string;label:string;sizeMB:number;ready:boolean}
export interface Health {version:string;models:Model[];cpuNote:string}
export interface History {id:string;name:string;updatedAt:number;analyzed:boolean}
export interface HistoryLists {recent:History[];hidden:History[]}
export interface Progress {percent:number;message:string}
export interface Update {status:string;message:string;channel:string;version?:string;notes?:string;percent?:number}
export interface ProjectResult {project:Project;audit:Audit;message?:string;captionFailures?:string[];editFailures?:string[]}
export type TranscriptOperation = 'exclude'|'restore';
export interface SequenceCutPreview {video:string;joinAt:number}
export interface CutPreview {
 video:string;joinAt:number;cutStart:number;cutEnd:number;before:[number,number];after:[number,number];
}
export interface SequenceConnection {video:string;joinAt:number;from:string;to:string}
export interface LongformSection {
 title:string;start:number;end:number;reason:string;previewTime:number;excerpt:string;retainedSeconds:number;
}
export interface LongformDraft {
 revision:number;targetSeconds:number;currentSeconds:number;hasDialogue:boolean;sections:LongformSection[];
 candidates:(Cut&{recommended:boolean})[];
}
export interface LongformResult {draft:LongformDraft;project?:Project;audit?:Audit}
export interface Bridge {
  call(action:string,data?:Record<string,unknown>):Promise<unknown>;
  dropped(file:File):Promise<Project>;
  droppedFiles(files:File[]):Promise<ProjectResult>;
  onProgress(callback:(progress:Progress)=>void):()=>void;
  onUpdate(callback:(update:Update)=>void):()=>void;
}
declare global {interface Window {localcut?:Bridge}}
