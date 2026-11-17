const test=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const path=require('node:path');
const {projectId,inside,validMedia,trustedSender,releaseConfig}=require('../desktop/electron/policy.cjs');
const {UpdateController}=require('../updater/controller.cjs');
test('IPC path and navigation policy',()=>{
 assert.throws(()=>projectId('../etc'));
 assert.equal(projectId('a'.repeat(32)),'a'.repeat(32));
 assert.equal(inside('/data/jobs','/data/jobs-other/video.mp4'),false);
 assert.equal(inside('/data/jobs','/data/jobs/a/video.mp4'),true);
 assert.equal(validMedia('x.exe'),false);assert.equal(validMedia('X.MP4'),true);
 assert.equal(trustedSender('https://evil.example','/app/index.html',null),false);
 assert.equal(trustedSender('http://127.0.0.1:5173.evil.example','/app/index.html','http://127.0.0.1:5173'),false);
 assert.equal(releaseConfig({owner:null,repo:null}),null);
 assert.throws(()=>releaseConfig({owner:'https://evil.example',repo:'x'}));
});
class FakeUpdater extends EventEmitter {
 setFeedURL(feed){this.feed=feed;}
 async checkForUpdates(){this.emit('checking-for-update');this.emit('update-available',{version:'0.2.0',releaseNotes:'<script>not HTML</script>'});}
 async downloadUpdate(){this.emit('update-downloaded',{version:'0.2.0'});}
 quitAndInstall(...options){this.installed=true;this.installOptions=options;}
}
test('updates require explicit download and idle install; no silent shutdown',async()=>{
 const updater=new FakeUpdater();let busy=true;
 const controller=new UpdateController(updater,{owner:'example',repo:'localcut'},()=>{},()=>busy);
 assert.equal(updater.autoDownload,false);assert.equal(updater.autoInstallOnAppQuit,false);
 assert.equal(updater.allowDowngrade,false);assert.equal(updater.feed.private,false);
 await controller.action('check','stable');assert.equal(controller.state.status,'available');
 assert.equal(controller.state.notes,'<script>not HTML</script>');
 await controller.action('download');assert.equal(controller.state.status,'downloaded');
 await assert.rejects(()=>controller.action('install'),/처리 중/);assert.equal(updater.installed,undefined);
 busy=false;await controller.action('install');assert.equal(updater.installed,true);assert.deepEqual(updater.installOptions,[true,true]);
});
test('unconfigured updates stay disabled and beta is opt-in',async()=>{
 const empty=new UpdateController(new FakeUpdater(),{},()=>{},()=>false);
 assert.equal((await empty.action('check')).status,'unconfigured');
 const updater=new FakeUpdater(),controller=new UpdateController(updater,{owner:'example',repo:'repo'},()=>{},()=>false);
 await assert.rejects(()=>controller.action('check','nightly'));
 await controller.action('check','beta');assert.equal(updater.allowPrerelease,true);
});
test('real GitHub provider empty feed is informational and can be checked again',async()=>{
 const {GitHubProvider}=require('electron-updater/out/providers/GitHubProvider');
 const updater=new FakeUpdater();
 const provider=new GitHubProvider({owner:'example',repo:'localcut'},updater,{platform:'win32',executor:{
  async request(options){
   assert.equal(options.hostname,'github.com');
   assert.equal(options.path,'/example/localcut/releases.atom');
   return '<feed xmlns="http://www.w3.org/2005/Atom"><title>Releases</title></feed>';
  }
 }});
 updater.checkForUpdates=async()=>{
  updater.emit('checking-for-update');
  try{return await provider.getLatestVersion();}
  catch(err){updater.emit('error',err);throw err;}
 };
 const controller=new UpdateController(updater,{owner:'example',repo:'localcut'},()=>{},()=>false);
 controller.set({version:'0.3.0',notes:'old notes',percent:70});
 const state=await controller.action('check','stable');
 assert.equal(state.status,'unpublished');
 assert.match(state.message,/공개된 업데이트 버전이 없습니다/);
 assert.equal(state.version,undefined);assert.equal(state.notes,undefined);assert.equal(state.percent,undefined);
 await assert.rejects(()=>controller.action('download'),/먼저 새 버전/);
 assert.equal(updater.installed,undefined);assert.equal(updater.autoDownload,false);
 updater.checkForUpdates=FakeUpdater.prototype.checkForUpdates.bind(updater);
 assert.equal((await controller.action('check')).status,'available');
});
test('coded empty-release rejection works without an updater error event',async()=>{
 const updater=new FakeUpdater();
 updater.checkForUpdates=async()=>{throw Object.assign(new Error('No release tag'),{code:'ERR_UPDATER_NO_PUBLISHED_VERSIONS'});};
 const controller=new UpdateController(updater,{owner:'example',repo:'localcut'},()=>{},()=>false);
 assert.equal((await controller.action('check','beta')).status,'unpublished');
 assert.equal(controller.state.channel,'beta');
});
test('network, missing assets and unrelated updater errors remain errors',async()=>{
 for(const err of [Object.assign(new Error('Connection reset'),{code:'ECONNRESET'}),
  Object.assign(new Error('latest.yml missing'),{code:'ERR_UPDATER_CHANNEL_FILE_NOT_FOUND'}),
  Object.assign(new Error('No XML release link'),{code:'ERR_XML_MISSED_ELEMENT'}),
  Object.assign(new Error('No published versions on GitHub'),{code:'EACCES'}),
  new Error('HTTP 404 while reading release metadata')]){
  const updater=new FakeUpdater();
  updater.checkForUpdates=async()=>{updater.emit('error',err);throw err;};
  const controller=new UpdateController(updater,{owner:'example',repo:'localcut'},()=>{},()=>false);
  await assert.rejects(()=>controller.action('check'),e=>e===err);
  assert.equal(controller.state.status,'error');
  assert.equal(updater.installed,undefined);
 }
});
