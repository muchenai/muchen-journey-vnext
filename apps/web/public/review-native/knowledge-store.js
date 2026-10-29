import {createCommunityApi} from './community-api.js?v=20261028-server';
const text=value=>String(value??'').trim();
export function validateKnowledgeUrl(value) {
  const raw = text(value);
  const fail = message => ({ valid: false, url: '', message });
  if (!raw) return fail('请填写在线文档链接');
  if (!/^https?:\/\//i.test(raw)) return fail('链接需以 http:// 或 https:// 开头');
  if (/[\s\\\u0000-\u001f\u007f]/.test(raw)) return fail('链接不能包含空格、反斜杠或控制字符');
  if (raw.length > 4000) return fail('链接过长，请使用文档的分享链接');
  try {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) return fail('请输入有效的在线文档链接');
    if (url.username || url.password) return fail('链接中不能包含账号或密码');
    return { valid: true, url: url.href, message: '' };
  } catch { return fail('链接格式不正确，请输入完整地址'); }
}

export function knowledgeFileType(filename) {
  const extension = text(filename).split('.').pop().toLowerCase();
  if (extension === 'pdf') return 'pdf';
  if (['doc', 'docx', 'docm', 'dot', 'dotx', 'odt', 'rtf'].includes(extension)) return 'word';
  if (['ppt', 'pptx', 'pptm', 'pps', 'ppsx', 'pot', 'potx', 'odp', 'key'].includes(extension)) return 'ppt';
  if (['xls', 'xlsx', 'xlsm', 'csv', 'ods', 'numbers'].includes(extension)) return 'sheet';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif', 'svg', 'tif', 'tiff', 'heic'].includes(extension)) return 'image';
  return 'other';
}

export function createKnowledgeStore({getCurrentUser}) {
 const api=createCommunityApi('knowledge',getCurrentUser,{categories:[],items:[]});
 return {...api,
  saveLink:values=>api.change('saveLink',values),updateItem:(id,values)=>api.change('updateItem',{...values,id}),
  removeItem:id=>api.change('removeItem',{id}),saveCategory:values=>api.change('saveCategory',values),removeCategory:id=>api.change('removeCategory',{id}),
  async uploadFiles(files,values={}) {
   files=Array.from(files||[]);if(!files.length||files.length>20)throw new Error('请选择 1～20 个文件。');
   if(files.some(f=>f.size>100*1024*1024))throw new Error('单个文件不能超过 100 MB。');
   const created=[];
   for(const file of files){
    let upload;
    try{
     upload=await api.raw('beginUpload',{fileName:file.name,size:file.size});
     for(let offset=0,position=0;offset<file.size;offset+=upload.chunkSize,position++){
      const bytes=new Uint8Array(await file.slice(offset,offset+upload.chunkSize).arrayBuffer());
      let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      await api.raw('uploadChunk',{id:upload.id,position,data:btoa(binary)});
     }
     created.push(await api.change('completeUpload',{...values,id:upload.id}));
    }catch(error){if(upload)await api.raw('cancelUpload',{id:upload.id}).catch(()=>{});throw new Error(`${file.name}：${error.message}${created.length?'；此前 '+created.length+' 份文件已保存。':''}`);}
   }
   return created;
  },
  async getFile(id){
   const item=api.snapshot().items.find(r=>r.id===id);if(!item)throw new Error('文件已不存在，请刷新。');
   const chunks=[];for(let position=0;position<Math.ceil(item.size/(512*1024));position++){
    const part=await api.raw('getChunk',{id,position});const raw=atob(part.data);chunks.push(Uint8Array.from(raw,c=>c.charCodeAt(0)));
   }
   return new Blob(chunks,{type:item.mimeType||'application/octet-stream'});
  }
 };
}
