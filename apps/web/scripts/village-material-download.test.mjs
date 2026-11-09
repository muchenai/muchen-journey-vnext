import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import {renderToStaticMarkup} from 'react-dom/server';

const task='00000000-0000-4000-8000-000000000001';
const source=readFileSync(new URL('../src/app/project29/villageMaterialDownload.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;

function load(fetchImpl=async()=>{throw Error('Unexpected request');}){
  const events=[];
  const links=[];
  const parent={
    appendChild(link){events.push('append');link.parentNode=this;return link;},
    append(link){this.appendChild(link);},
    removeChild(link){events.push('remove');link.parentNode=null;return link;},
  };
  const document={
    body:{appendChild(){throw Error('Download must stay in the supplied parent');}},
    createElement(tag){
      assert.equal(tag,'a');
      events.push('create');
      const attributes=new Map();
      const link={
        href:'',download:'',target:'',style:{},parentNode:null,
        setAttribute(name,value){attributes.set(name,String(value));this[name]=String(value);},
        getAttribute(name){return attributes.has(name)?attributes.get(name):(this[name]||null);},
        removeAttribute(name){attributes.delete(name);this[name]='';},
        click(){events.push('click');assert.equal(this.parentNode,parent);},
        remove(){events.push('remove');this.parentNode=null;},
      };
      links.push(link);
      return link;
    },
  };
  parent.ownerDocument=document;
  const location={origin:'http://localhost:3000',href:'http://localhost:3000/novice'};
  const window={document,location,open(){events.push('window.open');throw Error('Must not open another browser context');}};
  const mod={exports:{}};
  vm.runInNewContext(code,{module:mod,exports:mod.exports,fetch:fetchImpl,URL,Blob,Response,Headers,AbortController,DOMException,document,window,location,setTimeout,clearTimeout});
  return {...mod.exports,events,links,parent};
}

function attachment(body='course content',disposition="attachment; filename*=UTF-8''%E5%AD%A6%E4%B9%A0%E8%B5%84%E6%96%99.docx"){
  return new Response(body,{headers:{'Content-Disposition':disposition,'Content-Type':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}});
}

test('material is fetched in the current authenticated context without transferring a session in the URL',async()=>{
  const calls=[];
  const helper=load(async(...args)=>{calls.push(args);return attachment();});
  const signal=new AbortController().signal;
  const result=await helper.requestVillageMaterial(task,0,signal);
  assert.equal(calls.length,1);
  const [url,options]=calls[0];
  assert.equal(String(url),`/api/learner/village?task=${task}&material=0`);
  assert.equal(options.credentials,'same-origin');
  assert.equal(options.cache,'no-store');
  assert.equal(options.redirect,'error');
  assert.equal(options.signal,signal);
  assert.deepEqual([...new URL(url,'http://localhost:3000').searchParams.keys()],['task','material']);
  assert.doesNotMatch(String(url),/token|cookie|session|authorization/i);
  assert.equal(result.name,'学习资料.docx');
  assert.equal(await result.blob.text(),'course content');
  assert.deepEqual(helper.events,[]);
});

test('invalid task identifiers and material indices are rejected before any request',async()=>{
  let requests=0;
  const helper=load(async()=>{requests++;return attachment();});
  const signal=new AbortController().signal;
  for(const invalidTask of ['', '../../admin', `${task}&token=secret`, 'not-a-uuid']){
    await assert.rejects(async()=>helper.requestVillageMaterial(invalidTask,0,signal));
  }
  for(const index of [-1,100,0.5,NaN,Infinity]){
    await assert.rejects(async()=>helper.requestVillageMaterial(task,index,signal));
  }
  assert.equal(requests,0);
  assert.deepEqual(helper.events,[]);
});

test('both allowed index boundaries use the same protected endpoint',async()=>{
  const urls=[];
  const helper=load(async url=>{urls.push(String(url));return attachment();});
  for(const index of [0,99]) await helper.requestVillageMaterial(task,index,new AbortController().signal);
  assert.deepEqual(urls,[`/api/learner/village?task=${task}&material=0`,`/api/learner/village?task=${task}&material=99`]);
});

test('download filenames prefer UTF-8 filename* and remove path separators and control characters',async()=>{
  const original='../材料\\子目录\u0000\r\n.docx';
  const disposition=`attachment; filename="fallback.docx"; filename*=UTF-8''${encodeURIComponent(original)}`;
  const helper=load(async()=>attachment('course content',disposition));
  const result=await helper.requestVillageMaterial(task,0,new AbortController().signal);
  assert.match(result.name,/材料/);
  assert.doesNotMatch(result.name,/[\\/\u0000-\u001f\u007f]/);
  assert.notEqual(result.name,'fallback.docx');
  assert.ok(result.name.trim().length>0);
});

test('an attachment without a filename uses the learning-material fallback',async()=>{
  const helper=load(async()=>attachment('course content','attachment'));
  const result=await helper.requestVillageMaterial(task,0,new AbortController().signal);
  assert.equal(result.name,'学习材料');
});

for(const status of [401,403,404,500]){
  test(`HTTP ${status} cannot become a downloaded JSON error file`,async()=>{
    let blobReads=0;
    const helper=load(async()=>({
      ok:false,status,
      headers:new Headers({'Content-Type':'application/json'}),
      json:async()=>({error:'server error'}),
      text:async()=>'{"error":"server error"}',
      blob:async()=>{blobReads++;return new Blob(['{"error":"server error"}'],{type:'application/json'});},
    }));
    const request=()=>helper.requestVillageMaterial(task,0,new AbortController().signal);
    if(status===401) await assert.rejects(request,/登录/);
    else await assert.rejects(request);
    assert.equal(blobReads,0);
    assert.deepEqual(helper.events,[]);
  });
}

test('successful HTTP responses without an attachment header are not treated as materials',async()=>{
  for(const disposition of [null,'inline; filename="error.json"']){
    const headers=new Headers({'Content-Type':'application/json'});
    if(disposition) headers.set('Content-Disposition',disposition);
    const helper=load(async()=>new Response('{"error":"login required"}',{headers}));
    await assert.rejects(()=>helper.requestVillageMaterial(task,0,new AbortController().signal));
    assert.deepEqual(helper.events,[]);
  }
});

test('an empty attachment is rejected instead of saving an empty file',async()=>{
  const helper=load(async()=>attachment(''));
  await assert.rejects(()=>helper.requestVillageMaterial(task,0,new AbortController().signal));
  assert.deepEqual(helper.events,[]);
});

test('network errors and aborted requests do not create download links',async()=>{
  for(const failure of [new TypeError('Failed to fetch'),new DOMException('Aborted','AbortError')]){
    const helper=load(async()=>{throw failure;});
    await assert.rejects(()=>helper.requestVillageMaterial(task,0,new AbortController().signal));
    assert.deepEqual(helper.events,[]);
  }
});

test('a Blob download uses the supplied parent and download attribute without opening another window',()=>{
  const helper=load();
  const url='blob:http://localhost:3000/00000000-0000-4000-8000-000000000003';
  helper.startVillageMaterialDownload(url,'学习材料.docx',helper.parent);
  assert.equal(helper.links.length,1);
  assert.equal(helper.links[0].href,url);
  assert.equal(helper.links[0].download,'学习材料.docx');
  assert.equal(helper.links[0].target,'');
  assert.equal(helper.links[0].parentNode,null);
  assert.deepEqual(helper.events,['create','append','click','remove']);
});

test('the download launcher refuses URLs that would navigate to protected APIs or external browsers',()=>{
  const helper=load();
  for(const url of [
    `/api/learner/village?task=${task}&material=0`,
    'https://journey.muchenai.com/api/learner/village?token=secret',
    'https://external.example/material.docx',
    'data:text/plain,material',
    'javascript:alert(1)',
    '',
  ]) assert.throws(()=>helper.startVillageMaterialDownload(url,'学习材料.docx',helper.parent));
  assert.deepEqual(helper.events,[]);
});

function loadMaterials({react=React,downloadHelpers={},extras={}}={}){
  const componentSource=readFileSync(new URL('../src/app/project29/VillageTaskMaterials.tsx',import.meta.url),'utf8');
  const componentCode=ts.transpileModule(componentSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const mod={exports:{}};
  const dependencies={'react':react,'react/jsx-runtime':jsxRuntime,'./villageMaterialDownload':downloadHelpers};
  vm.runInNewContext(componentCode,{module:mod,exports:mod.exports,require:name=>{
    assert.ok(Object.hasOwn(dependencies,name),`Unexpected component dependency: ${name}`);
    return dependencies[name];
  },URL,Blob,AbortController,window:{setTimeout},...extras});
  return mod.exports.VillageTaskMaterials;
}

test('file and image materials render download buttons while external document links remain links',()=>{
  let requests=0;
  const VillageTaskMaterials=loadMaterials({downloadHelpers:{requestVillageMaterial:()=>{requests++;},startVillageMaterialDownload:()=>{requests++;}}});
  const materials=[
    {type:'file',name:'培训资料.docx',url:`/api/learner/village?task=${task}&material=0`,text:''},
    {type:'image',name:'学习流程.png',url:`/api/learner/village?task=${task}&material=1`,text:''},
    {type:'link',name:'在线文档',url:'https://example.feishu.cn/docx/course',text:''},
    {type:'text',name:'阅读说明',url:'',text:'先阅读材料，再完成任务。'},
  ];
  const html=renderToStaticMarkup(React.createElement(VillageTaskMaterials,{task:{id:task,versionId:'version-1',materials}}));
  assert.equal((html.match(/<button\b/g)||[]).length,2);
  assert.match(html,/aria-label="下载学习材料：培训资料.docx"/);
  assert.match(html,/aria-label="下载学习材料：学习流程.png"/);
  assert.equal((html.match(/<a\b/g)||[]).length,1);
  assert.match(html,/href="https:\/\/example.feishu.cn\/docx\/course" target="_blank" rel="noopener noreferrer"/);
  assert.doesNotMatch(html,/\/api\/learner\/village/);
  assert.match(html,/<strong>阅读说明<\/strong>/);
  assert.match(html,/先阅读材料，再完成任务。/);
  assert.equal(requests,0);
});

test('repeated material clicks share one pending request and closing the task aborts it before saving',async()=>{
  const refs=[];
  const cleanup=[];
  const requests=[];
  let resolveRequest;
  let downloads=0;
  let objectUrls=0;
  const pending=new Promise(resolve=>{resolveRequest=resolve;});
  const react={...React,
    useRef(value){const ref={current:value};refs.push(ref);return ref;},
    useState(value){return [value,()=>{}];},
    useEffect(effect){cleanup.push(effect());},
  };
  const VillageTaskMaterials=loadMaterials({react,downloadHelpers:{
    requestVillageMaterial(taskId,index,signal){requests.push({taskId,index,signal});return pending;},
    startVillageMaterialDownload(){downloads++;},
  },extras:{URL:{createObjectURL(){objectUrls++;return 'blob:http://localhost:3000/test';},revokeObjectURL(){}}}});
  const materialTree=VillageTaskMaterials({task:{id:task,versionId:'version-1',materials:[{type:'file',name:'培训资料.docx',url:'/api/learner/village',text:''}]}});
  const downloadComponent=materialTree.props.children[0].props.children[0];
  const downloadTree=downloadComponent.type(downloadComponent.props);
  refs[0].current={};
  const button=downloadTree.props.children[0];
  button.props.onClick();
  button.props.onClick();
  assert.equal(requests.length,1);
  assert.equal(requests[0].taskId,task);
  assert.equal(requests[0].index,0);
  assert.equal(requests[0].signal.aborted,false);
  for(const dispose of cleanup) dispose();
  assert.equal(requests[0].signal.aborted,true);
  resolveRequest({blob:new Blob(['materials']),name:'培训资料.docx'});
  await pending;
  await Promise.resolve();
  assert.equal(objectUrls,0);
  assert.equal(downloads,0);
});
