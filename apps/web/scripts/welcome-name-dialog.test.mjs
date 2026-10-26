import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {createRequire} from 'node:module';

const nativeRequire=createRequire(import.meta.url);
function mount(name,onSave){
  const states=[name,'',false];let index=0;
  const react={useEffect(){},useRef:value=>({current:value}),useState:()=>{
    const i=index++;return [states[i],value=>{states[i]=value}];
  }};
  const source=ts.transpileModule(readFileSync(new URL('../src/app/project29/WelcomeNameDialog.tsx',import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}
  }).outputText;
  const compiledModule={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})')(name=>name==='react'?react:nativeRequire(name),compiledModule,compiledModule.exports);
  const tree=compiledModule.exports.WelcomeNameDialog({open:true,decoration:null,onSave});
  const form=tree.props.children.find(child=>child?.type==='form');
  return {states,submit:()=>form.props.onSubmit({preventDefault(){}})};
}
test('welcome name dialog waits for real save and rejects duplicate submissions',async()=>{
  let finish,calls=[];
  const view=mount('  小晨  ',name=>{calls.push(name);return new Promise(resolve=>{finish=resolve})});
  const first=view.submit();
  assert.equal(view.states[2],true);await view.submit();assert.deepEqual(calls,['小晨']);
  finish({error:'服务器暂不可用'});await first;
  assert.equal(view.states[1],'服务器暂不可用');assert.equal(view.states[2],false);
});
test('blank name never calls the save action',async()=>{
  const view=mount('   ',()=>{throw Error('must not save')});await view.submit();
  assert.equal(view.states[1],'请输入您的真实姓名');
});
test('network failure preserves the form for retry',async()=>{
  const view=mount('小晨',async()=>{throw Error('network')});await view.submit();
  assert.equal(view.states[1],'姓名保存失败，请稍后重试。');assert.equal(view.states[0],'小晨');assert.equal(view.states[2],false);
});
