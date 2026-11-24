// Stream only the requested bytes of an already granted local media file.
const fs=require('node:fs/promises');
const path=require('node:path');
const {Readable}=require('node:stream');
function byteRange(value,size){
 if(!value)return {start:0,end:size-1,partial:false};
 const match=/^bytes=(\d*)-(\d*)$/.exec(value);
 if(!match||(!match[1]&&!match[2])||size===0)return null;
 let start,end;
 if(!match[1]){
  const suffix=Number(match[2]);
  if(!Number.isSafeInteger(suffix)||suffix<=0)return null;
  start=Math.max(0,size-suffix);end=size-1;
 }else{
  start=Number(match[1]);end=match[2]?Number(match[2]):size-1;
  if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start>=size||end<start)return null;
  end=Math.min(end,size-1);
 }
 return {start,end,partial:true};
}
async function mediaResponse(filename,request){
 if(!['GET','HEAD'].includes(request.method))return new Response(null,{status:405,headers:{Allow:'GET, HEAD'}});
 const handle=await fs.open(filename,'r');
 try{
  const stat=await handle.stat();
  if(!stat.isFile())throw new Error('Not a media file');
  const range=byteRange(request.headers.get('range'),stat.size);
  const headers={'Accept-Ranges':'bytes','Content-Type':({'.mp4':'video/mp4','.mov':'video/quicktime','.avi':'video/x-msvideo','.mkv':'video/x-matroska'})[path.extname(filename).toLowerCase()]||'application/octet-stream'};
  if(!range){await handle.close();return new Response(null,{status:416,headers:{...headers,'Content-Range':`bytes */${stat.size}`,'Content-Length':'0'}});}
  const {start,end,partial}=range;
  headers['Content-Length']=String(Math.max(0,end-start+1));
  if(partial)headers['Content-Range']=`bytes ${start}-${end}/${stat.size}`;
  if(request.method==='HEAD'||stat.size===0){await handle.close();return new Response(null,{status:partial?206:200,headers});}
  const body=Readable.toWeb(handle.createReadStream({start,end,autoClose:true}));
  return new Response(body,{status:partial?206:200,headers});
 }catch(error){await handle.close().catch(()=>{});throw error;}
}
module.exports={mediaResponse};
