const {contextBridge, ipcRenderer, webUtils} = require('electron');
const invoke = (action, data) => ipcRenderer.invoke('localcut', {action,...data});
contextBridge.exposeInMainWorld('localcut', {
  call: (action,data={})=>invoke(action,data),
  dropped: file=>invoke('import',{path:webUtils.getPathForFile(file)}),
  onProgress: callback=>{const fn=(_,data)=>callback(data);ipcRenderer.on('progress',fn);return ()=>ipcRenderer.removeListener('progress',fn);},
  onUpdate: callback=>{const fn=(_,data)=>callback(data);ipcRenderer.on('update',fn);return ()=>ipcRenderer.removeListener('update',fn);}
});
