const {_electron:electron}=require(require('node:path').resolve('test-driver/node_modules/playwright'));
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
async function main(){
 const directory=path.resolve('test-results/installed-updater');await fs.mkdir(directory,{recursive:true});
 const response=await fetch(`https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/releases?per_page=1`,{
  headers:{Authorization:`Bearer ${process.env.GH_TOKEN}`,Accept:'application/vnd.github+json'}
 });
 assert.equal(response.status,200,'GitHub Releases API must be accessible');
 const releases=await response.json();assert.ok(Array.isArray(releases));
 const app=await electron.launch({executablePath:process.env.LOCALCUT_TEST_INSTALLED_EXE,
  args:[`--user-data-dir=${await fs.mkdtemp(path.join(os.tmpdir(),'localcut-updater-'))}`],timeout:30000});
 try{
  const page=await app.firstWindow();page.setDefaultTimeout(30000);
  await page.waitForFunction(()=>!!window.localcut);
  const health=await page.evaluate(()=>window.localcut.call('health'));
  assert.equal(health.version,process.env.LOCALCUT_EXPECT_VERSION);
  await page.getByRole('button',{name:'모델 · 업데이트',exact:true}).click();
  await page.evaluate(()=>{window.__updateChecks=[];window.__stopUpdateChecks=window.localcut.onUpdate(state=>window.__updateChecks.push(state.status));});
  await page.getByRole('button',{name:'업데이트 확인',exact:true}).click();
  await page.waitForFunction(()=>window.__updateChecks.includes('checking') &&
   ['unpublished','current','available','error'].includes(window.__updateChecks.at(-1)),null,{timeout:60000});
  const state=await page.evaluate(()=>window.localcut.call('updateStatus'));
  if(releases.length===0){
   assert.equal(state.status,'unpublished',state.message);
   assert.match(state.message,/공개된 업데이트 버전이 없습니다/);
  }else{
   assert.ok(['current','available'].includes(state.status),JSON.stringify(state));
  }
  await page.getByText(state.message,{exact:true}).waitFor();
  assert.equal(await page.locator('.banner.error').count(),0,'Update check must not produce a global task error');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(button=>button.textContent==='업데이트 확인' && !button.disabled));
  assert.equal(await page.getByRole('button',{name:'업데이트 확인',exact:true}).isEnabled(),true);
  const observed=await page.evaluate(()=>{window.__stopUpdateChecks();return window.__updateChecks;});
  await page.screenshot({path:path.join(directory,'settings.png'),fullPage:true});
  const report={passed:true,version:health.version,repository:process.env.GITHUB_REPOSITORY,
   buildSource:process.env.LOCALCUT_EXPECT_BUILD_SHA,publicReleaseCount:releases.length,
   updateStatus:state.status,message:state.message,observed,
   scope:'Real Windows installed app, UI click, IPC and live GitHub release check; no update download or install'};
  await fs.writeFile(path.join(directory,'result.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
 }finally{await app.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
