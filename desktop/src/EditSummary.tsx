import type {CutSummary,Project} from './types';

export function EditSummary({summary,project,formatTime}:{summary:CutSummary;project:Project;formatTime:(seconds:number)=>string}){
 const current=!!project.output&&project.output.revision===project.revision;
 return <section className="panel edit-summary" aria-label="편집 적용 요약">
  <div className="edit-summary-grid">
   <div><span>원본 길이</span><strong>{formatTime(summary.sourceDuration)}</strong></div>
   <div><span>예상 결과 길이</span><strong>{formatTime(summary.outputDuration)}</strong></div>
   <div><span>삭제 적용 {summary.appliedCount}개</span><strong>{formatTime(summary.removedDuration)} 단축</strong></div>
   <div><span>검토 후 적용</span><strong>{summary.reviewCount}개 보존 중</strong></div>
  </div>
  {summary.noCutReason&&<p className="edit-summary-note" role="status">{summary.noCutReason}</p>}
  {summary.analysisNeedsRefresh&&<p className="edit-summary-note">편집 모드가 변경됐습니다. 다시 분석해야 새 기준으로 편집점을 찾습니다.</p>}
  <p className="edit-summary-output">{project.output?
   current?`현재 편집의 실제 출력 길이: ${formatTime(project.output.duration)}`:`이전 출력 길이: ${formatTime(project.output.duration)} · 저장하면 최신 편집으로 다시 출력합니다.`:
   'MP4 저장을 누르면 현재 편집으로 출력한 후 저장합니다.'}</p>
 </section>;
}
