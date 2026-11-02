import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const require=createRequire(import.meta.url);
test('lint compatibility uses patched glob matching for legacy and named imports',()=>{
  const result=execFileSync(process.execPath,['--require','./scripts/eslint-minimatch-compat.cjs','-e',`
    const m=require('minimatch');
    const result=[m('src/page.tsx','**/*.{ts,tsx}'),m.minimatch('src/page.tsx','**/*.tsx'),
      new m.Minimatch('**/node_modules/**').match('src/page.tsx'),
      m.match(['a.js','b.ts'], '**/*.ts')];
    console.log(JSON.stringify(result));
  `],{cwd:root,encoding:'utf8'});
  assert.deepEqual(JSON.parse(result),[true,true,false,['b.ts']]);
  assert.equal(require('minimatch/package.json').version,'11.0.3');
});

test('ESLint still reports violations with patched minimatch',async()=>{
  require('./eslint-minimatch-compat.cjs');
  const {ESLint}=require('eslint');
  const linter=new ESLint({overrideConfigFile:true,overrideConfig:{rules:{'no-debugger':'error'}}});
  const [result]=await linter.lintText('debugger;',{filePath:'lint-probe.js'});
  assert.equal(result.errorCount,1);
  assert.equal(result.messages[0].ruleId,'no-debugger');
});
