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
 quitAndInstall(){this.installed=true;}
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
 busy=false;await controller.action('install');assert.equal(updater.installed,true);
});
test('unconfigured updates stay disabled and beta is opt-in',async()=>{
 const empty=new UpdateController(new FakeUpdater(),{},()=>{},()=>false);
 assert.equal((await empty.action('check')).status,'unconfigured');
 const updater=new FakeUpdater(),controller=new UpdateController(updater,{owner:'example',repo:'repo'},()=>{},()=>false);
 await assert.rejects(()=>controller.action('check','nightly'));
 await controller.action('check','beta');assert.equal(updater.allowPrerelease,true);
});
