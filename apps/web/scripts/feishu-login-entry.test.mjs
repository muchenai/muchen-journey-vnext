import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

const nativeRequire=createRequire(import.meta.url);
function compile(relative,overrides={}){
  const source=ts.transpileModule(readFileSync(new URL(relative,import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const compiledModule ={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})')(
    name=>name in overrides?overrides[name]:nativeRequire(name),compiledModule,compiledModule.exports,
  );
  return compiledModule.exports;
}

// Exercise the existing pure detector, not a duplicate test-only UA rule.
const feishu=compile('../src/lib/feishu-client-login.ts');
function joinRoute(userAgent,summary){
  const requestHeaders=new Headers();
  if(userAgent!==undefined)requestHeaders.set('user-agent',userAgent);
  const encodedSummary=summary?Buffer.from(JSON.stringify(summary)).toString('base64url'):undefined;
  return compile('../src/app/join/page.tsx',{
    'next/headers':{
      headers:async()=>requestHeaders,
      cookies:async()=>({get:name=>name==='journey_next_join_summary'&&encodedSummary?{value:encodedSummary}:undefined}),
    },
    '@/lib/feishu-client-login':feishu,
    '@/app/project29/App':{default:()=>null},
  });
}

test('join page passes the request Feishu environment before the first client render',async()=>{
  for(const ua of [
    'Mozilla/5.0 Lark/7.50.0',
    'Mozilla/5.0 Lark/7.50.0 WebApp',
    'Mozilla/5.0 Android Feishu/7.50.0',
    'Mozilla/5.0 (iPhone) Feishu/7.50.0',
  ]){
    const route=joinRoute(ua);
    assert.equal(route.dynamic,'force-dynamic');
    const page=await route.default({searchParams:Promise.resolve({})});
    assert.equal(page.props.feishuClient,true,ua);
    assert.equal(page.props.initialScreen,'login');
    assert.equal(page.props.joinPhase,'feishu');
    assert.equal(page.props.joinError,'');
  }
});

test('browser or missing UA keeps phone login available despite Feishu-looking query values',async()=>{
  for(const ua of [undefined,'','Mozilla/5.0 Chrome/140.0 Safari/537.36','LarkishBrowser/1.0']){
    const route=joinRoute(ua);
    const page=await route.default({searchParams:Promise.resolve({feishuClient:'true',feishu_app_entry:'1'})});
    assert.equal(page.props.feishuClient,false,String(ua));
    assert.equal(page.props.joinPhase,'feishu');
  }
});

test('join page environment detection preserves invite stages and authentication errors',async()=>{
  const ua='Mozilla/5.0 Lark/7.50.0';
  const invite=await joinRoute(ua).default({searchParams:Promise.resolve({method:'invite'})});
  assert.equal(invite.props.joinPhase,'invite');
  const identity=await joinRoute(ua,{flow:'JOIN',purpose:'LEARNER',expires_at:'2026-12-01T00:00:00Z'}).default({
    searchParams:Promise.resolve({method:'invite'}),
  });
  assert.equal(identity.props.joinPhase,'identity');
  const error=await joinRoute(ua).default({searchParams:Promise.resolve({auth_error:'IDENTITY_REVOKED'})});
  assert.equal(error.props.feishuClient,true);
  assert.equal(error.props.joinPhase,'feishu');
  assert.equal(error.props.joinError,'该飞书身份已停用，请联系管理员。');
});
