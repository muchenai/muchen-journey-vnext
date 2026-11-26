import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createAcademyWorkspace } from '../public/review-native/academy-workspace.js';
import { chapterReflections, learnerRoster, renderWorkspace } from '../public/review-native/academy-workspace-views.js';
import { createEditor } from '../public/review-native/academy-workspace-editor.js';
import { courseIssues, materialControl } from '../public/review-native/academy-course-validation.js';
import { renderVillagePublishType } from '../public/review-native/publish-content-type.js';
import { REVIEW_CAMPS } from '../public/review-native/core.js';
import { canConfigureTask } from '../public/review-native/task-publication-access.js';

const ui = {refresh() {}, icon: () => ''};
const catalog = {actorId:'owner',people:[{id:'owner',name:'课程负责人'}],
  assignments:{ownerId:'owner',adminIds:[],reviewers:[]},learners:[],tags:[],courses:[],progress:[],canManageLegacy:true};

test('only the academy progress toolbar opens the read-only learner roster',()=>{
  const data={...catalog,learners:[{id:'current',name:'示例学员',code:'AC-OLD'}]};
  const html=learnerRoster(data);
  assert.match(html,/学员名单/);
  assert.match(html,/示例学员/);
  assert.doesNotMatch(html,/AC-OLD|学习码|<button/);
  const state={tab:'progress',search:''};
  const academy=renderWorkspace(data,state,ui.icon,'academy');
  assert.match(academy,/data-aw-learners="">学员名单</);
  assert.doesNotMatch(academy,/学习码/);
  const village=renderWorkspace(data,state,ui.icon,'village');
  assert.doesNotMatch(village,/data-aw-learners|学员名单|学习码/);
  assert.match(village,/data-aw-filter="progressCourse"/);
  assert.match(village,/data-aw-reload="">刷新</);
});

test('village progress shows the current directory identity on its own learner row',()=>{
  const progress = {learnerName:'同名学员',courseId:'course',courseTitle:'测试',courseRevision:2,watchedSeconds:72.55,
    percent:1,status:'learning',completedChapters:0,chapterCount:1};
  const data = {...catalog, progressCourses:[{id:'course',title:'测试'}], learners:[
    {id:'current',memberProfile:{name:'飞书名',avatar:'https://example.com/photo.jpg',employeeNo:'M123',
      jobTitle:'讲师<高级>',departmentPaths:['研发中心 / 开发部','研发中心 / 培训部'],departments:['开发部']}},
    {id:'namesake',memberProfile:null},
  ],progress:[{...progress,learnerId:'current'},{...progress,learnerId:'namesake'}]};
  const render = scope=>renderWorkspace(data,{tab:'progress',search:''},ui.icon,scope);
  const rows = render('village').match(/<tr data-aw-searchable=.*?<\/tr>/gs);
  assert.equal(rows.length,2);
  assert.match(rows[0],/src="https:\/\/example\.com\/photo\.jpg"[^>]+referrerpolicy="no-referrer"/);
  assert.match(rows[0],/<strong>飞书名<\/strong><small>工号：M123<\/small><small>职务：讲师&lt;高级&gt;<\/small><small>部门：研发中心 \/ 开发部；研发中心 \/ 培训部/);
  assert.match(rows[0],/1 分 12 秒/);
  assert.match(rows[0],/data-aw-reflections="course" data-learner-id="current" data-course-revision="2">查看心得</);
  assert.match(rows[1],/data-aw-reflections="course" data-learner-id="namesake"/);
  assert.match(rows[1],/<td>同名学员<\/td>/);
  assert.doesNotMatch(rows[1],/飞书名|M123|aw-progress-person/);
  assert.doesNotMatch(render('academy'),/aw-progress-person|飞书名|M123|查看心得/);
});

test('chapter reflections preserve submission order, line breaks and literal markup',()=>{
  const html=chapterReflections({learnerName:'学员甲',courseTitle:'必修课程',chapters:[
    {title:'起步',text:'  一句话\n<b>学员的原文</b>  ',submittedAt:'2026-11-26T02:03:04Z'},
    {title:'练习<script>',text:null,submittedAt:null},
  ]});
  assert.match(html,/学员甲 · 必修课程/);
  assert.match(html,/<h3>第 1 章 · 起步<\/h3>[\s\S]*提交于 [\s\S]*<p class="aw-preserve">  一句话\n&lt;b&gt;学员的原文&lt;\/b&gt;  <\/p>[\s\S]*第 2 章 · 练习&lt;script&gt;[\s\S]*未提交心得/);
});

test('only a reflection click loads its row and a closed dialog ignores the response',async t=>{
  let finish;
  const calls=[];
  t.mock.method(globalThis,'fetch',async (url,init)=>{
    calls.push({url,init});
    if (url.endsWith('?camp=village')) return Response.json({ok:true,data:catalog});
    return new Promise(resolve=>{finish=resolve;});
  });
  const body={innerHTML:''};
  const modal=Object.assign(new EventTarget(),{
    classList:{add(){}},setAttribute(){},
    querySelector:selector=>selector==='[data-aw-reflection-body]'?body:null,
  });
  const workspace=createAcademyWorkspace({ui:{...ui,openModal(html,ready){ready(modal);}},legacy:{},scope:'village'});
  const button={dataset:{awReflections:'course',learnerId:'current',courseRevision:'3'}};
  await workspace.activate();
  workspace.bind({querySelectorAll:selector=>selector==='[data-aw-reflections]'?[button]:[],querySelector:()=>null});
  assert.equal(calls.length,1);
  button.onclick();
  assert.equal(calls[1].url,'/api/review-native/course-workspace/village-reflections?courseId=course&learnerId=current&courseRevision=3');
  assert.equal(calls[1].init.signal.aborted,false);
  modal.dispatchEvent(new Event('review-close'));
  assert.equal(calls[1].init.signal.aborted,true);
  finish(Response.json({ok:true,data:{courseTitle:'旧课程',learnerName:'学员',chapters:[]}}));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(body.innerHTML,'');
});

test('progress filters use report access, including courses without learners and a revoked selection',()=>{
  const courses = [
    {id:'own',title:'我的草稿标题',status:'published'},
    {id:'review',title:'仅可审核课程',status:'published'},
  ];
  const data = {...catalog,courses,progressCourses:[{id:'own',title:'我的在架标题'},{id:'empty',title:'暂无学员的课程'}],
    progress:[
      {courseId:'own',courseTitle:'我的在架标题',learnerName:'本课学员'},
      {courseId:'review',courseTitle:'仅可审核课程',learnerName:'其他学员'},
    ]};
  for(const scope of ['academy','village']){
    const state={tab:'progress',search:'',progressCourse:'review'};
    const html=renderWorkspace(data,state,ui.icon,scope);
    assert.match(html,/value="" selected>全部课程/);
    assert.match(html,/我的在架标题/);
    assert.match(html,/暂无学员的课程/);
    assert.match(html,/本课学员/);
    assert.doesNotMatch(html,/仅可审核课程|其他学员|我的草稿标题/);
    assert.doesNotMatch(renderWorkspace({...data,progressCourses:[]},state,ui.icon,scope),/我的在架标题|本课学员/);
  }
});

test('denied workspace refresh clears the last successful report',async t=>{
  const data = {...catalog,courses:[{id:'c1',title:'先前可见课程',tags:[],author:{id:'owner'}}]};
  const fetch = t.mock.method(globalThis,'fetch',async()=>Response.json({ok:true,data}));
  const workspace=createAcademyWorkspace({ui,legacy:{}});
  await workspace.activate();
  assert.match(workspace.render(),/先前可见课程/);
  fetch.mock.mockImplementation(async()=>Response.json({ok:false,error:'权限已撤销'},{status:403}));
  await workspace.activate();
  assert.match(workspace.render(),/权限已撤销/);
  assert.doesNotMatch(workspace.render(),/先前可见课程|学习情况/);
});

test('course validation orders fields and preserves the different draft and publication requirements',()=>{
  const editor=createEditor(null,'village');
  editor.course.minutes=0;
  editor.course.rewardXp=-1;
  assert.deepEqual(courseIssues(editor,false).map(i=>i.selector),['[name=title]','[name=minutes]','[name=rewardXp]']);
  editor.course.minutes=10;
  editor.course.rewardXp=20;
  editor.course.title='已有标题';
  assert.equal(courseIssues(editor,false).length,0);
  assert.deepEqual(courseIssues(editor,true).map(i=>i.selector),[materialControl]);
  editor.scope='academy';
  assert.deepEqual(courseIssues(editor,true).map(i=>i.selector),[materialControl,'[name=contentText]','[name=rubric]']);
});

test('incomplete section in another chapter is identified by its stable IDs for focus after navigation',()=>{
  const editor=createEditor(null,'village');
  editor.course.title='必修课程';
  const chapter=editor.course.chapters[0], assigned=chapter.sections[0];
  assigned.materialIds=['m1'];
  editor.course.materials.push({id:'m1',kind:'link'});
  const empty={id:'new-sec',title:'',materialIds:[]};
  editor.course.chapters.push({id:'new-ch',title:'第二章',sections:[empty],homework:'',exam:''});
  assert.deepEqual(courseIssues(editor,true).map(({selector,chapter,section})=>[selector,chapter,section]),[
    ['[name=sectionTitle]','new-ch','new-sec'],[materialControl,'new-ch','new-sec'],
  ]);
  empty.title='第二小节';
  editor.linkDrafts.set(empty,{linkUrl:'https://example.com'});
  assert.deepEqual(courseIssues(editor,false).map(i=>i.selector),['[name=linkUrl]']);
});

test('authenticated workspace renders the catalog, registered account and retained legacy entry',async t=>{
  const calls=[];
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    calls.push({path,options});
    return Response.json({ok:true,data:catalog});
  });
  const workspace=createAcademyWorkspace({ui,legacy:{}});
  await workspace.activate();
  assert.equal(calls[0].path,'/api/review-native/course-workspace');
  assert.equal(calls[0].options.credentials,'same-origin');
  const html=workspace.render();
  assert.match(html,/课程负责人/);
  assert.match(html,/发布审核/);
  assert.match(html,/学习情况/);
  assert.match(html,/原有课程与员工分享记录/);
  assert.doesNotMatch(html,/data-aw-actor/);
});

test('village entry opens its chapter editor with an independent draft and a 2 GB video upload',async t=>{
  t.mock.method(globalThis,'fetch',async path=>{
    assert.equal(path,'/api/review-native/course-workspace?camp=village');
    return Response.json({ok:true,data:catalog});
  });
  const workspace=createAcademyWorkspace({ui,legacy:{},scope:'village'});
  await workspace.startPublishing(true);
  const html=workspace.render();
  assert.match(html,/新增必修课程/);
  assert.match(html,/上传学习任务材料/);
  assert.match(html,/每个视频最大 2 GB/);
  assert.equal(workspace.publicationCourse().required,true);
  assert.ok(workspace.publicationCourse().creationId);
  assert.equal(workspace.publicationCourse().chapters.length,1);
});

test('village management keeps the publishing controls behind the new publication button',async t=>{
  t.mock.method(globalThis,'fetch',async()=>Response.json({ok:true,data:catalog}));
  const source=readFileSync(new URL('../public/review-native/app.js',import.meta.url),'utf8');
  function appFunction(name) {
    const match=source.match(new RegExp('^function '+name+'\\([\\s\\S]*?^\\}', 'm'));
    assert.ok(match,`Missing application function ${name}`);
    return match[0];
  }
  const context=vm.createContext({ui:{...ui,isSuperAdmin:true},REVIEW_CAMPS,canConfigureTask,renderVillagePublishType});
  for(const name of ['renderVillageCoursePublication','renderCampField','openVillagePublicationChooser']){
    vm.runInContext(appFunction(name),context);
  }
  const workspace=createAcademyWorkspace({ui,legacy:{},scope:'village',onNewPublication:context.openVillagePublicationChooser});
  context.villageCourses=workspace;
  await workspace.showCourseList();
  const list=context.renderVillageCoursePublication();
  assert.match(list,/新手村任务管理/);
  assert.match(list,/data-aw-new/);
  assert.doesNotMatch(list,/data-course-camp|data-publish-kind/);
  assert.equal(workspace.publicationCourse(),undefined);

  const button={};
  workspace.bind({querySelectorAll:selector=>selector==='[data-aw-new]'?[button]:[],querySelector:()=>null});
  const types=['required','elective'].map(value=>({value}));
  let html, opened=false;
  const actions=[];
  Object.assign(context,{
    villagePublishPage:'publish/village-courses',
    openModal(contents,ready) {
      html=contents;
      opened=true;
      ready({setAttribute(){},querySelectorAll:()=>types,querySelector:()=>({})});
    },
    closeModal(){opened=false;},
    navigate:(...args)=>actions.push(['navigate',...args]),
    taskWorkflow:{start:(...args)=>actions.push(['start',...args])},
  });
  for(const type of types){
    button.onclick();
    assert.equal(opened,true);
    assert.match(html,/<input[^>]+value="novice"[^>]+\bchecked\b/);
    assert.doesNotMatch(html,/<input[^>]+value="exploration"[^>]+\bchecked\b/);
    assert.deepEqual([...html.matchAll(/data-publish-kind="([^"]+)"[^>]*>/g)].map(match=>match[1]),['required','elective']);
    assert.doesNotMatch(html,/data-publish-kind="[^"]+"[^>]*\bchecked\b/);
    assert.deepEqual(actions,[]);
    type.checked=true;
    type.onchange();
    assert.equal(opened,false);
    assert.deepEqual(actions.pop(),type.value==='required' ? ['navigate','publish/village-courses','required'] : ['start',null,'novice']);
  }
});
