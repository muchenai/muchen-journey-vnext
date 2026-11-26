import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import {renderToStaticMarkup} from 'react-dom/server';
const nativeRequire=createRequire(import.meta.url);
function compile(file,overrides){
  const source=ts.transpileModule(readFileSync(new URL('../src/app/'+file,import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}
  }).outputText;
  const compiledModule ={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})')(name=>name in overrides?overrides[name]:nativeRequire(name),compiledModule,compiledModule.exports);
  return compiledModule.exports;
}
function routes(needsNickname,explorationOnly=true){
  const requests=[];
  const api={learnerPageRequest:async path=>{
    requests.push(path);
    if(path.endsWith('learner-profile'))return {needs_nickname:needsNickname,exploration_only:explorationOnly};
    if(path.endsWith('session'))return {display_name:needsNickname?'探索者':'小晨'};
    if(path.endsWith('current-action'))return {action_type:'WAIT',journey:null};
    if(path.endsWith('completion-code'))return {status:'LOCKED'};
    throw Error('Unexpected API '+path);
  }};
  const navigation={redirect:path=>{throw Error('REDIRECT '+path)}};
  const experience=compile('project-ui/experience-data.ts',{'server-only':{},'next/navigation':navigation,'@/lib/server/api':api,'./review-feedback':{},'./exploration-links':{}});
  const access=compile('../lib/learner-module-access.ts',{});
  const notice=compile('project-ui/CompanyLoginNotice.tsx',{
    '@/lib/learner-module-access':access,
    './company-login-notice.module.css':{default:{page:'page',card:'card'}},
  });
  const overrides={'@/lib/server/local-preview':{localVillagePreviewEnabled:()=>true},'@/lib/learner-module-access':access,'next/navigation':navigation,'@/lib/server/api':api,'@/app/project-ui/experience-data':experience,'@/app/project-ui/CompanyLoginNotice':notice,'@/app/project29/App':{default:()=>null}};
  return {requests,home:compile('app/page.tsx',overrides).default,profile:compile('app/profile/page.tsx',overrides).default};
}
test('new phone learner sees introduction before required name dialog',async()=>{
  const {home}=routes(true);
  const intro=await home({searchParams:Promise.resolve({})});
  assert.equal(intro.props.initialScreen,'welcome');assert.equal(intro.props.joinPhase,'nickname');
  const dashboard=await home({searchParams:Promise.resolve({view:'dashboard'})});
  assert.equal(dashboard.props.initialScreen,'dashboard');assert.equal(dashboard.props.joinPhase,'nickname');
});
test('saved names keep introduction and do not reopen nickname setup',async()=>{
  const {home}=routes(false);
  for(const view of [undefined,'dashboard']){
    const page=await home({searchParams:Promise.resolve({view})});
    assert.equal(page.props.initialScreen,view??'welcome');assert.equal(page.props.joinPhase,'invite');
  }
});
test('unfinished nickname task deep links return through the introduction',async()=>{
  const {home,profile}=routes(true);
  await assert.rejects(home({searchParams:Promise.resolve({view:'tasks'})}),/REDIRECT \/app\/profile/);
  assert.equal((await profile()).props.initialScreen,'welcome');
  assert.equal((await profile()).props.explorationOnly,true);
});

test('phone learners opening company module links see the login prompt in place before loading any learning data', async () => {
  for (const needsNickname of [false, true]) {
    for (const view of ['village', 'academy', 'guild']) {
      const phone = routes(needsNickname, true);
      const page = await phone.home({ searchParams: Promise.resolve({ view, course: 'saved-course', task: 'saved-task' }) });
      assert.ok(renderToStaticMarkup(page).includes('请用公司认证的飞书账号进行登录和使用'));
      assert.deepEqual(phone.requests, ['/api/v1/me/learner-profile']);
    }
  }
});

test('company learners can still open each module and saved course links', async () => {
  const company = routes(false, false);
  for (const view of ['village', 'academy', 'guild']) {
    const searchParams = Promise.resolve({ view, course: 'saved-course', task: 'saved-task', section: 'profile' });
    const page = await company.home({ searchParams });
    assert.equal(page.props.initialScreen, view);
    assert.equal(page.props.explorationOnly, false);
    if (view !== 'guild') assert.equal(page.props.academyEntry.courseId, 'saved-course');
  }
});
