const path = require('node:path');
const {fileURLToPath} = require('node:url');
const ID = /^[a-f0-9]{32}$/;
const EXTENSIONS = new Set(['.mp4','.mov','.avi','.mkv']);
function projectId(value) {
  if (typeof value !== 'string' || !ID.test(value)) throw new Error('잘못된 작업 ID입니다.');
  return value;
}
function inside(root, filename) {
  const relative = path.relative(root, filename);
  return relative !== '' && !relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative);
}
function validMedia(filename) {return typeof filename === 'string' && EXTENSIONS.has(path.extname(filename).toLowerCase());}
function trustedSender(url, rendererFile, devUrl) {
  try {
    if (devUrl && new URL(url).origin === new URL(devUrl).origin) return true;
    return url.startsWith('file:') && fileURLToPath(url.split('#')[0]) === rendererFile;
  } catch { return false; }
}
function releaseConfig(config) {
  if (!config.owner || !config.repo) return null;
  if (!/^[A-Za-z0-9-]+$/.test(config.owner) || !/^[A-Za-z0-9_.-]+$/.test(config.repo) || ['.','..'].includes(config.repo)) throw new Error('업데이트 저장소 설정이 잘못되었습니다.');
  return {provider:'github',owner:config.owner,repo:config.repo,private:false};
}
module.exports = {projectId,inside,validMedia,trustedSender,releaseConfig};
