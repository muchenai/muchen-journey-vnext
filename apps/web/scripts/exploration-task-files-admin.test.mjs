import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {validateTask} from '../public/review-native/core.js';
import {taskIssue} from '../public/review-native/task-field-limits.js';
import {taskView,taskWrite,detailView} from '../public/review-native/native-model.js';
import {ApiStore,createJourneyService} from '../public/review-native/native-api.js';
import {copyAsNewTask,hasUnsavedChanges} from '../public/review-native/task-workflow.js';
import {createMaterialEditor} from '../public/review-native/material-editor.js';
import {taskResourceLinks,explorationTaskResourceErrors} from '../public/review-native/exploration-completion.js';
import {renderPublishMaterials} from '../public/review-native/publish-materials.js';
import {createPublicationReviewController} from '../public/review-native/publication-review.js';
import {openTask} from '../public/review-native/library.js';
import {openSubmission} from '../public/review-native/review.js';
import {uploadExplorationMaterial,EXPLORATION_MATERIAL_MAX_BYTES} from '../public/review-native/exploration-material-files.js';

const id='00000000-0000-4000-8000-000000000001';
const link=(name,url='https://example.com/learning')=>({id:crypto.randomUUID(),type:'link',name,url});
const file=(name='培训题目.pdf',size=100)=>({id,name,type:'file',url:`exploration-material:${id}`,mime:'application/pdf',size});
const task=(extra={})=>({id,camp:'exploration',completionMode:'assessment',assessmentUrl:'',taskFiles:[file()],materials:[link('学习材料')],
  title:'测试探索营任务',summary:'阅读学习材料并完成任务文档中的题目。',order:1,reviewMode:'manual',badges:[],rubric:[],...extra});

test('publish issues identify the field and row without parsing the displayed message',()=>{
  const draft=task({title:'',summary:'',reviewMode:'ai',passScore:105,
    taskFiles:[link('', 'http://example.com')],rubric:[{id:'d',name:'',points:0,description:''}]});
  const issues=validateTask(draft,taskIssue);
  assert.deepEqual(issues.map(problem=>problem.message),validateTask(draft));
  for(const field of ['title','summary','passScore'])assert.ok(issues.some(problem=>problem.field===field));
  for(const field of ['taskFiles','rubric.name','rubric.points','rubric.description'])
    assert.ok(issues.some(problem=>problem.field===field && problem.index===0));
});

test('No modes keep learning materials and serialize no inactive task resources without mutating local edits',()=>{
  for(const completionMode of ['learning','checkin']){
    const draft=task({completionMode,assessmentUrl:'not a valid URL'});
    const before=structuredClone(draft);
    const written=taskWrite(draft);
    assert.deepEqual(validateTask(draft),[]);
    assert.deepEqual(written.materials,draft.materials);
    assert.deepEqual(written.taskFiles,[]);
    assert.equal(written.assessmentUrl,'');
    assert.deepEqual(draft,before);
    const html=renderPublishMaterials(draft.materials,draft);
    assert.doesNotMatch(html,/培训题目\.pdf|发布任务文件|not a valid URL/);
  }
});

test('Yes publication requires a task resource independently of study materials and accepts legacy test links',()=>{
  assert.deepEqual(validateTask(task()),[]);
  const learningOnly=task({taskFiles:[]});
  assert.deepEqual(validateTask(learningOnly),['请上传任务文件，或填写已有的测试链接']);
  assert.deepEqual(validateTask(task({materials:[]})),['请至少添加一份学习材料']);
  assert.deepEqual(validateTask(task({taskFiles:[],assessmentUrl:'https://example.com/test'})),[]);
  assert.deepEqual(validateTask(task({taskFiles:[link('任务文档','https://example.com/questions')]})),[]);
  assert.ok(validateTask(task({assessmentUrl:'javascript:alert(1)'})).some(message=>message.includes('HTTPS')));
});

test('task file count, blank names, link security and byte limits match publication readiness',()=>{
  assert.deepEqual(explorationTaskResourceErrors(task({taskFiles:Array.from({length:20},()=>file())})),[]);
  assert.match(explorationTaskResourceErrors(task({taskFiles:Array.from({length:21},()=>file())})).join(''),/20 份任务文件/);
  for(const size of [0,-1,EXPLORATION_MATERIAL_MAX_BYTES+1,1.5]){
    assert.match(explorationTaskResourceErrors(task({taskFiles:[file('题目.pdf',size)]})).join(''),/100 MB/);
  }
  assert.deepEqual(explorationTaskResourceErrors(task({taskFiles:[file('题目.pdf',EXPLORATION_MATERIAL_MAX_BYTES)]})),[]);
  assert.match(explorationTaskResourceErrors(task({taskFiles:[{...file(),name:'　 '}]})).join(''),/名称/);
  for(const url of ['http://example.com','https://user:secret@example.com','javascript:alert(1)']){
    assert.match(explorationTaskResourceErrors(task({taskFiles:[link('题目',url)]})).join(''),/HTTPS/);
  }
});

test('adapters and copy preserve separate task files, and editing a copy does not change the original',()=>{
  const original=task({status:'published',version:2,versionId:'v2'});
  assert.deepEqual(taskView(taskWrite(original)).taskFiles,original.taskFiles);
  const copied=copyAsNewTask(original,{id:'copy',order:3});
  assert.deepEqual(copied.taskFiles,original.taskFiles);
  assert.deepEqual(copied.materials,original.materials);
  copied.taskFiles[0].name='复制题目.pdf';
  assert.equal(original.taskFiles[0].name,'培训题目.pdf');
  assert.equal(copied.id,'copy');
  assert.equal(copied.versionId,undefined);
  assert.equal(hasUnsavedChanges({...original,taskFiles:[file('已更改题目.pdf')]},original,{}),true);
  assert.deepEqual(taskView(task({taskFiles:undefined})).taskFiles,[]);
});

function editorHarness(draft){
  const fields={name:{value:'',setAttribute(){},addEventListener(){},focus(){}},url:{value:'',setAttribute(){},addEventListener(){},focus(){}}};
  const nodes=Object.fromEntries(['#material-name-error','#material-url-error','#material-save-error','[data-cancel-material]'].map(key=>[key,{}]));
  const form={elements:{namedItem:key=>fields[key]}};nodes['#material-form']=form;
  const store={data:{draft}},state={saves:0,messages:[]};
  const open=createMaterialEditor({store,openModal(html,ready){state.html=html;ready({querySelector:key=>nodes[key]});},
    closeModal(){},saveDraft(){state.saves++;return true;},refresh(){},toast(message){state.messages.push(message);}});
  return {open,fields,state,nodes,submit(){form.onsubmit({preventDefault(){}});}};
}

test('task file edits and links change only the task collection and retain stored bytes',()=>{
  const draft=task(),originalMaterials=structuredClone(draft.materials),originalFile=structuredClone(draft.taskFiles[0]);
  const editor=editorHarness(draft);
  editor.open(0,{collection:'taskFiles'});
  assert.match(editor.state.html,/编辑任务文件/);
  editor.fields.name.value=' 新题目.pdf ';editor.submit();
  assert.deepEqual(draft.taskFiles,[{...originalFile,name:'新题目.pdf'}]);
  assert.deepEqual(draft.materials,originalMaterials);
  editor.open(null,{collection:'taskFiles'});
  editor.fields.name.value='题目链接';editor.fields.url.value='https://example.com/questions';editor.submit();
  assert.equal(draft.taskFiles.length,2);
  assert.deepEqual(draft.materials,originalMaterials);
  editor.open(null,{collection:'taskFiles'});
  editor.fields.name.value=' ';editor.submit();
  assert.equal(draft.taskFiles.length,2);
  assert.equal(editor.nodes['#material-name-error'].textContent,'任务文件名称不能只包含空格');
});

test('task links and legacy test URL are deduplicated after study links for every publish confirmation',()=>{
  const draft=task({taskFiles:[file(),link('题目文档','https://example.com/questions'),link('共用文档')],assessmentUrl:'https://example.com/test'});
  assert.deepEqual(taskResourceLinks(draft),['https://example.com/learning','https://example.com/questions','https://example.com/test']);
  const html=renderPublishMaterials(draft.materials,draft);
  assert.match(html,/学习材料（1）/);assert.match(html,/任务文件（3）/);
  assert.match(html,new RegExp(`/api/review-native/exploration/materials/${id}`));
  assert.deepEqual([...html.matchAll(/data-verified-link="(\d+)"/g)].map(match=>match[1]),['0','1','2']);
  assert.match(html,/题目文档/);assert.match(html,/打开培训测试链接/);
});

test('draft persistence allows unfinished Yes tasks; final publication verifies task resources',async()=>{
  const store=new ApiStore();store.capabilities={isSuperAdmin:true};store.operatorId='operator';store.data={tasks:[]};store.save=()=>{};store.refresh=async()=>{};
  const before=globalThis.fetch,requests=[];
  globalThis.fetch=async(url,options)=>{
    const command=JSON.parse(options.body);requests.push(command);
    return {ok:true,status:200,json:async()=>({ok:true,data:command.task})};
  };
  try{
    const empty=task({taskFiles:[]});
    await store.saveTask(empty);
    assert.deepEqual(requests[0].task.taskFiles,[]);
    const draft=task({taskFiles:[link('题目','https://example.com/questions')]});
    store.members=[{id:'reviewer',roles:['REVIEWER']}];
    const service=createJourneyService({store});
    await assert.rejects(service.tasks.publish(draft,'reviewer',['https://example.com/learning'],'key'),/任务链接/);
    assert.equal(requests.length,1);
    await service.tasks.publish(draft,'reviewer',taskResourceLinks(draft),'key');
    assert.deepEqual(requests[1].task.taskFiles,draft.taskFiles);
    assert.deepEqual(requests[1].payload.verified,taskResourceLinks(draft));
  }finally{globalThis.fetch=before;}
});

test('task-file uploads use authenticated raw-byte storage and report task-specific errors',async()=>{
  const before=globalThis.fetch,uploaded=new File(['题目'],'题目.docx',{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
  let request;
  globalThis.fetch=async(url,options)=>{request={url,options};return {ok:true,json:async()=>({ok:true,data:{...file(uploaded.name,uploaded.size),mime:uploaded.type}})};};
  try{
    const result=await uploadExplorationMaterial(uploaded,{label:'任务'});
    assert.equal(request.options.body,uploaded);
    assert.equal(result.url,`exploration-material:${id}`);
    await assert.rejects(uploadExplorationMaterial({name:'空题目.pdf',size:0},{label:'任务'}),/非空的任务文件/);
    await assert.rejects(uploadExplorationMaterial({name:'大题目.pdf',size:EXPLORATION_MATERIAL_MAX_BYTES+1},{label:'任务'}),/100 MB/);
  }finally{globalThis.fetch=before;}
});

test('library and publication review show task files separately with correct download offsets',()=>{
  const draft=task(),store={data:{submissions:[]}};
  let library;
  openTask(draft,store,{openModal(html){library=html;},toast(){}});
  assert.match(library,/任务文件 <span class="count-pill">1/);
  assert.match(library,/data-task-file-download="0"/);
  const request={id:'publication',status:'pending',task:draft,submittedBy:{id:'owner',name:'发布人'}};
  store.data.publicationRequests=[request];
  let publication;
  const ui={isSuperAdmin:true,icon:()=>'',openModal(html){publication=html;},toast(){}};
  const controller=createPublicationReviewController({store,service:{},ui});
  const page={contains:()=>true,querySelector:()=>({})};
  controller.bind({querySelector:()=>page});
  page.onclick({target:{closest:()=>({dataset:{pubOpen:'publication'}})}});
  assert.match(publication,/是否需要做任务<strong>需要/);
  assert.match(publication,/任务文件 <small>1/);
  assert.match(publication,/data-pub-download="1"/);
});

test('reviewer sees fixed-version task files and test URL rather than the latest task resources',async()=>{
  const latest=task({completionMode:'learning',taskFiles:[file('新题目.pdf')],assessmentUrl:'https://example.com/new'});
  const base={id:'review',taskId:id,studentName:'学员',camp:'exploration',status:'passed',reviewMode:'manual'};
  const detail={revision:2,status:'COMPLETED',submission_body:'完成的答案',task_title:'固定版本任务',task_purpose:'旧要求',
    task_learning_materials:[{title:'固定学习材料',body:'材料正文'},{title:'旧题目.pdf',source_label:'任务题目文件'},{title:'培训测试',source_label:'任务测试入口'}],
    task_task_files:[file('旧题目.pdf')],task_assessment_url:'https://example.com/old',task_completion_mode:'assessment'};
  const reviewed=detailView(base,detail,latest,'http://localhost:3000');
  assert.equal(reviewed.taskSnapshot.taskFiles[0].name,'旧题目.pdf');
  assert.equal(reviewed.taskSnapshot.assessmentUrl,'https://example.com/old');
  assert.equal(reviewed.taskSnapshot.completionMode,'assessment');
  assert.deepEqual(reviewed.taskSnapshot.materials.map(item=>item.name),['固定学习材料']);
  const store={data:{submissions:[reviewed]},getTask:()=>latest,loadSubmission:async()=>{}};
  let html;
  await openSubmission(store,{reviewCamp:'exploration',openModal(value){html=value;},toast(){}},'review');
  assert.match(html,/旧题目\.pdf/);assert.match(html,/https:\/\/example.com\/old/);
  assert.doesNotMatch(html,/新题目\.pdf|https:\/\/example.com\/new/);
});

test('real editor offers separate task upload and guards publish while any upload is pending',async()=>{
  const app=await readFile(new URL('../public/review-native/app.js',import.meta.url),'utf8');
  assert.match(app,/是否需要做任务/);assert.match(app,/id="task-file-upload"/);assert.match(app,/上传任务文件/);
  assert.match(app,/data-material-collection="\$\{collection\}"/);
  assert.match(app,/async function publish\(\) \{[\s\S]*?if\(materialUploadsPending\)/);
  assert.match(app,/target=event\.target\.closest\('#task-files'\)\?'taskFiles':'materials'/);
});
