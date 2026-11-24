const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {mediaResponse}=require('../desktop/electron/media.cjs');
async function fixture(t,bytes=Buffer.from('0123456789abcdef')){
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'localcut-range-'));
 t.after(()=>fs.rm(root,{recursive:true,force:true,maxRetries:5,retryDelay:50}));
 const file=path.join(root,'영상.mp4');await fs.writeFile(file,bytes);return file;
}
test('local video range responses match actual bytes and allow seeking',async t=>{
 const file=await fixture(t);
 const full=await mediaResponse(file,new Request('http://local/video'));
 assert.equal(full.status,200);assert.equal(full.headers.get('accept-ranges'),'bytes');
 assert.equal(full.headers.get('content-type'),'video/mp4');assert.equal(await full.text(),'0123456789abcdef');
 for(const [range,expected,contentRange] of [['bytes=4-7','4567','bytes 4-7/16'],['bytes=12-','cdef','bytes 12-15/16'],['bytes=-3','def','bytes 13-15/16'],['bytes=14-999','ef','bytes 14-15/16']]){
  const response=await mediaResponse(file,new Request('http://local/video',{headers:{Range:range}}));
  assert.equal(response.status,206);assert.equal(response.headers.get('content-range'),contentRange);
  assert.equal(Number(response.headers.get('content-length')),expected.length);assert.equal(await response.text(),expected);
 }
});
test('invalid local ranges are rejected and HEAD contains no payload',async t=>{
 const file=await fixture(t);
 for(const range of ['bytes=16-','bytes=8-3','bytes=-0','bytes=-','bytes=0-1,4-5','bytes=999999999999999999999-','bad']){
  const response=await mediaResponse(file,new Request('http://local/video',{headers:{Range:range}}));
  assert.equal(response.status,416,range);assert.equal(response.headers.get('content-range'),'bytes */16');assert.equal(await response.text(),'');
 }
 const head=await mediaResponse(file,new Request('http://local/video',{method:'HEAD',headers:{Range:'bytes=2-5'}}));
 assert.equal(head.status,206);assert.equal(head.headers.get('content-length'),'4');assert.equal(await head.text(),'');
 const empty=await fixture(t,Buffer.alloc(0));
 const result=await mediaResponse(empty,new Request('http://local/video'));
 assert.equal(result.status,200);assert.equal(await result.text(),'');
});
