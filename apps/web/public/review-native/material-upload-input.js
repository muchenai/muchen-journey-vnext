import { learningMaterialFileMime } from './exploration-material-files.js';

export function hasTransferredFiles(transfer) {
  return !!transfer&&(Array.from(transfer.types||[]).includes('Files')||Array.from(transfer.items||[]).some(item=>item.kind==='file')||transfer.files?.length>0);
}

// Prefer the ordered item stream, then add only files not already represented
// there. Duplicate counts are consumed across sources, never within one source.
export function transferredFiles(transfer) {
  const files=[], errors=[], represented=new Map(), folders=new Set();
  const signature=file=>`${file.name||''}\0${file.size}\0${file.type||''}`;
  for(const item of Array.from(transfer?.items||[])){
    if(item.kind!=='file')continue;
    let entry, file;
    try {entry=item.webkitGetAsEntry?.();} catch { /* Clipboard items may not expose entries. */ }
    if(entry?.isDirectory){folders.add(entry.name);errors.push(`“${entry.name}”是文件夹，请打开后选择其中的文件。`);continue;}
    try {file=item.getAsFile();} catch {errors.push('有一个文件无法读取，请重新选择文件上传。');continue;}
    if(!file){errors.push('有一个文件无法读取，请重新选择文件上传。');continue;}
    files.push(file);const key=signature(file);represented.set(key,(represented.get(key)||0)+1);
  }
  for(const file of Array.from(transfer?.files||[])){
    if(folders.has(file.name))continue;
    const key=signature(file), count=represented.get(key)||0;
    if(count){represented.set(key,count-1);continue;}
    files.push(file);
  }
  const hasFiles=hasTransferredFiles(transfer);
  if(hasFiles&&!files.length&&!errors.length)errors.push('未能读取其中的文件，请改用“上传文件”重新选择。');
  return {files,errors,hasFiles};
}

let nameSequence=0;
export function normalizeLearningMaterialFile(file,{source='select',names=new Set()}={}) {
  if(!file||typeof file.size!=='number'||typeof file.slice!=='function')throw new Error('无法读取这个文件，请重新选择。');
  if(file.webkitRelativePath?.includes('/'))throw new Error('暂不支持上传文件夹，请单独选择其中的文件。');
  const type=learningMaterialFileMime(file);
  let name=String(file.name||'').replace(/[\\/\x00-\x1f\x7f]/g,'_').trim();
  const screenshot=source==='paste'&&type.startsWith('image/')&&/^(?:image|blob|clipboard|pasted[-_ ]?image|screenshot|截图)(?:[-_ ]?\d*)?(?:\.[^.]+)?$/i.test(name);
  if(!name||screenshot){
    const extension=({'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/webp':'webp','image/avif':'avif','image/bmp':'bmp'})[type]||'bin';
    const stamp=new Date().toISOString().replace(/\D/g,'').slice(0,17);
    name=`${type.startsWith('image/')?'粘贴图片':'学习材料'}-${stamp}-${++nameSequence}.${extension}`;
  }
  if(name.length>240)throw new Error('文件名不能超过 240 个字符，请重命名后上传。');
  const extension=name.match(/\.[a-z0-9]{1,12}$/i)?.[0]||'', stem=extension?name.slice(0,-extension.length):name;
  let unique=name, index=2;
  while(names.has(unique))unique=`${stem.slice(0,220-extension.length)} (${index++})${extension}`;
  names.add(unique);
  return unique===file.name&&type===file.type?file:new File([file],unique,{type,lastModified:file.lastModified||Date.now()});
}

export function isMaterialPasteTarget(target) {
  if(!target?.closest||target.closest('#task-rubric,input,textarea,select'))return false;
  const editable=target.closest('[contenteditable]');
  return !editable||editable.getAttribute('contenteditable')==='false';
}
