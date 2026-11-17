const {releaseConfig} = require('../desktop/electron/policy.cjs');
class UpdateController {
  constructor(updater, config, notify, busy) {
    this.updater=updater; this.notify=notify; this.busy=busy;
    this.state={status:'unconfigured',message:'배포 저장소를 연결하면 업데이트를 받을 수 있습니다.',channel:'stable'};
    const feed=releaseConfig(config);
    if (!feed) return;
    updater.autoDownload=false;
    updater.autoInstallOnAppQuit=false;
    updater.allowDowngrade=false;
    updater.allowPrerelease=false;
    updater.setFeedURL(feed);
    this.state={status:'idle',message:'업데이트를 확인할 수 있습니다.',channel:'stable'};
    updater.on('checking-for-update',()=>this.set({status:'checking',message:'새 버전 확인 중'}));
    updater.on('update-available',info=>this.set({status:'available',version:info.version,notes:this.notes(info.releaseNotes),message:'새 버전이 있습니다.'}));
    updater.on('update-not-available',()=>this.set({status:'current',message:'최신 버전입니다.'}));
    updater.on('download-progress',p=>this.set({status:'downloading',percent:p.percent,message:'업데이트 다운로드 중'}));
    updater.on('update-downloaded',info=>this.set({status:'downloaded',version:info.version,message:'다운로드 완료. 편집 작업을 마친 후 설치할 수 있습니다.'}));
    updater.on('error',err=>this.fail(err));
  }
  notes(value) {
    // Always rendered as plain text; release notes never become executable HTML.
    return typeof value==='string' ? value.slice(0,10000) : Array.isArray(value) ? value.map(v=>v.note||'').join('\n').slice(0,10000) : '';
  }
  set(value) {this.state={...this.state,...value};this.notify(this.state);return this.state;}
  fail(err) {
    // GitHubProvider's empty Atom feed reports a missing XML entry with this exact message.
    // Do not treat missing assets, HTTP failures or network errors as an empty release list.
    const unpublished=err?.code==='ERR_UPDATER_NO_PUBLISHED_VERSIONS' ||
      ((!err?.code || err.code==='ERR_XML_MISSED_ELEMENT') && err?.message==='No published versions on GitHub');
    return this.set({status:unpublished?'unpublished':'error',version:undefined,notes:undefined,percent:undefined,
      message:unpublished?'아직 공개된 업데이트 버전이 없습니다. 현재 프로그램은 계속 사용할 수 있습니다.':
        '업데이트 실패. 네트워크와 저장 공간을 확인한 뒤 다시 시도해 주세요. '+err.message});
  }
  async action(action,channel) {
    if(this.state.status==='unconfigured') return this.state;
    if(action==='check') {
      if(['downloading','downloaded'].includes(this.state.status)) return this.state;
      if(channel && !['stable','beta'].includes(channel)) throw new Error('지원하지 않는 업데이트 채널입니다.');
      if(channel) {this.updater.allowPrerelease=channel==='beta';this.set({channel});}
      try {
        await this.updater.checkForUpdates();
      } catch(err) {
        const state=this.fail(err);
        // Return a normal IPC result for an empty feed instead of a global task-error banner.
        if(state.status!=='unpublished') throw err;
      }
    } else if(action==='download') {
      if(this.state.status!=='available') throw new Error('먼저 새 버전을 확인해 주세요.');
      // Change state before await so concurrent clicks cannot start another download.
      this.set({status:'downloading',percent:0,message:'업데이트 다운로드 중'});
      await this.updater.downloadUpdate(); // electron-updater verifies SHA-512 and configured publisher signatures.
    } else if(action==='install') {
      if(this.busy()) throw new Error('영상 처리 중에는 업데이트를 설치할 수 없습니다. 작업이 끝난 뒤 다시 시도해 주세요.');
      if(this.state.status!=='downloaded') throw new Error('업데이트 다운로드를 먼저 완료해 주세요.');
      this.updater.quitAndInstall(true,true);
    } else throw new Error('지원하지 않는 업데이트 명령입니다.');
    return this.state;
  }
}
module.exports={UpdateController};
