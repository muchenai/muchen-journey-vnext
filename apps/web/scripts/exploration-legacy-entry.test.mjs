import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const nativeRequire=createRequire(import.meta.url);
const root=new URL('../src/app/',import.meta.url);
function page(file,experience){
  const calls=[];
  const source=ts.transpileModule(readFileSync(new URL(file,root),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const dependencies={
    'next/navigation':{redirect:target=>{throw Error('REDIRECT '+target)}},
    '@/lib/server/api':{},
    '@/lib/server/local-preview':{localVillagePreviewEnabled:()=>false},
    '@/app/project29/App':{default:()=>null},
    '@/app/project-ui/experience-data':{loadProjectExperience:async (...args)=>{
      calls.push(args);return {learnerName:'原学员',experience,needsNickname:false};
    }},
  };
  const compiledModule={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})')(
    name=>name in dependencies?dependencies[name]:nativeRequire(name),compiledModule,compiledModule.exports,
  );
  return {render:compiledModule.exports.default,calls};
}

test('legacy task listing retains original progress and the original task UI while the default catalog stays dynamic',async()=>{
  const experience={journeyTasks:[{assignmentId:'original-assignment',position:1}]};
  const home=page('app/page.tsx',experience);
  const legacy=await home.render({searchParams:Promise.resolve({view:'legacy-tasks'})});
  assert.equal(legacy.props.initialScreen,'tasks');
  assert.equal(legacy.props.configurableExploration,false);
  assert.equal(legacy.props.experience,experience);
  assert.deepEqual(home.calls[0],[undefined,false]);
  for(const view of ['tasks','dashboard']){
    const current=await home.render({searchParams:Promise.resolve({view})});
    assert.equal(current.props.configurableExploration,true);
  }
});

test('the already released village deep link remains available without a local preview flag',async()=>{
  const home=page('app/page.tsx',{journeyTasks:[]});
  const village=await home.render({searchParams:Promise.resolve({view:'village'})});
  assert.equal(village.props.initialScreen,'village');
  assert.equal(village.props.localVillagePreview,false);
  assert.equal(village.props.configurableExploration,true);
});

test('original assignment deep links retain review and submission screens and never use the new catalog',async()=>{
  const experience={assignmentId:'original-assignment',journeyTasks:[]};
  const task=page('app/tasks/[assignmentId]/page.tsx',experience);
  for(const [view,screen] of [[undefined,'detail'],['evidence','view'],['review','view']]){
    const result=await task.render({params:Promise.resolve({assignmentId:'original-assignment'}),searchParams:Promise.resolve({view})});
    assert.equal(result.props.configurableExploration,false);
    assert.equal(result.props.initialScreen,screen);
    assert.equal(result.props.experience,experience);
  }
  assert.deepEqual(task.calls,[['original-assignment'],['original-assignment'],['original-assignment']]);
});

test('returning from an original task targets its retained task list and can return to the new dashboard',()=>{
  const source=readFileSync(new URL('project29/App.tsx',root),'utf8');
  assert.match(source,/target === "tasks" && !configurableExploration \? "legacy-tasks" : target/);
  assert.match(source,/!configurableExploration && target === "dashboard"[\s\S]*?window\.location\.assign\("\/app\?view=dashboard"\)/);
});
