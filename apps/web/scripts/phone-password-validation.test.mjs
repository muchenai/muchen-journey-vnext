import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const nativeRequire=createRequire(import.meta.url);
function compile(relative,overrides={}){
  const source=ts.transpileModule(readFileSync(new URL(relative,import.meta.url),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022},
  }).outputText;
  const compiledModule={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})')(
    name=>name in overrides?overrides[name]:nativeRequire(name),compiledModule,compiledModule.exports,
  );
  return compiledModule.exports;
}

const validation=compile('../src/lib/phone-password-validation.ts');
const {phonePasswordError,confirmPhonePasswordError}=validation;
const {PhonePasswordField}=compile('../src/app/project-ui/PhonePasswordField.tsx',{
  '@/lib/phone-password-validation':validation,
});
const longPaste='pasted-password-that-is-longer-than-eleven-characters';

test('password validation rejects empty, whitespace, short and overlength values',()=>{
  for(const [value,error] of [
    ['','请输入密码'],
    ['      ','密码不能包含空格'],
    ['12 345','密码不能包含空格'],
    ['\t12345','密码不能包含空格'],
    ['123456\n','密码不能包含空格'],
    ['12345','密码至少需要 6 个字符'],
    ['123456789012','密码最多支持 11 个字符'],
    [longPaste,'密码最多支持 11 个字符'],
  ])assert.equal(phonePasswordError(value),error,JSON.stringify(value));
});

test('password validation preserves the existing inclusive 6 and 11 character boundaries',()=>{
  assert.equal(validation.PHONE_PASSWORD_MIN_LENGTH,6);
  assert.equal(validation.PHONE_PASSWORD_MAX_LENGTH,11);
  for(const value of ['123456','abcdefghijk','abc!@#']){
    assert.equal(phonePasswordError(value),'',value);
    assert.equal(confirmPhonePasswordError(value,value),'',value);
  }
});

test('confirmation reports its own invalid value before a password mismatch',()=>{
  for(const [value,error] of [
    ['','请再次输入密码'],
    ['abc def','确认密码不能包含空格'],
    ['short','确认密码至少需要 6 个字符'],
    ['123456789012','确认密码最多支持 11 个字符'],
    [longPaste,'确认密码最多支持 11 个字符'],
    ['654321','两次输入的密码不一致，请重新确认'],
  ])assert.equal(confirmPhonePasswordError(value,'123456'),error,JSON.stringify(value));
  assert.equal(confirmPhonePasswordError(longPaste,longPaste),'确认密码最多支持 11 个字符',
    'Matching invalid values must not bypass validation');
});

test('reset password errors retain the new-password and confirmation wording',()=>{
  for(const [value,error] of [
    ['','请输入新密码'],
    ['abc def','新密码不能包含空格'],
    ['short','新密码至少需要 6 个字符'],
    [longPaste,'新密码最多支持 11 个字符'],
  ])assert.equal(phonePasswordError(value,'新密码'),error);
  for(const [value,error] of [
    ['','请再次输入新密码'],
    ['abc def','确认新密码不能包含空格'],
    ['short','确认新密码至少需要 6 个字符'],
    [longPaste,'确认新密码最多支持 11 个字符'],
    ['654321','两次输入的密码不一致，请重新确认'],
  ])assert.equal(confirmPhonePasswordError(value,'123456','新密码'),error);
});

function fieldProps(value,overrides={}){
  return {
    label:'密码',value,onChange(){},placeholder:'请输入密码',autoComplete:'current-password',
    disabled:false,shown:false,onToggle(){},visibilityLabel:'密码',
    error:phonePasswordError(value),validate:false,...overrides,
  };
}
function renderField(value,overrides={}){
  return renderToStaticMarkup(React.createElement(PhonePasswordField,fieldProps(value,overrides)));
}
function inputTag(html){
  const input=html.match(/<input\b[^>]*>/)?.[0];
  assert.ok(input,'The password input must render');
  return input;
}
function assertVisibleError(html,error){
  const input=inputTag(html);
  const describedBy=input.match(/aria-describedby="([^"]+)"/)?.[1];
  const alert=html.match(/<p\b[^>]*role="alert"[^>]*>([^<]*)<\/p>/)?.[0];
  assert.ok(describedBy,'An invalid input must describe its error');
  assert.ok(alert,'A visible error must announce itself as an alert');
  assert.match(input,/aria-invalid="true"/);
  assert.equal(alert.match(/\bid="([^"]+)"/)?.[1],describedBy);
  assert.ok(alert.includes(`>${error}</p>`),error);
}
function assertNoVisibleError(html){
  assert.match(inputTag(html),/aria-invalid="false"/);
  assert.doesNotMatch(html,/role="alert"|aria-describedby=|password-input-invalid/);
}

test('12 characters and long pasted passwords remain complete and show an immediate accessible error',()=>{
  for(const value of ['123456789012',longPaste]){
    const html=renderField(value);
    const input=inputTag(html);
    assert.ok(input.includes(`value="${value}"`),'The full input must remain visible in the field value');
    assert.doesNotMatch(input,/\bmaxlength=/i,'The browser must not silently truncate pasted passwords');
    assertVisibleError(html,'密码最多支持 11 个字符');
  }
});

test('whitespace errors appear immediately before blur or submit',()=>{
  const html=renderField('abc def');
  assert.ok(inputTag(html).includes('value="abc def"'));
  assertVisibleError(html,'密码不能包含空格');
});

test('untouched empty and short fields wait for interaction instead of showing errors on first render',()=>{
  for(const value of ['','12345'])assertNoVisibleError(renderField(value));
});

test('submit validation reveals empty and short field errors with matching accessible descriptions',()=>{
  for(const [value,error] of [['','请输入密码'],['12345','密码至少需要 6 个字符']]){
    assertVisibleError(renderField(value,{validate:true}),error);
  }
});

test('valid boundary values stay intact and error-free after submit validation',()=>{
  for(const value of ['123456','abcdefghijk']){
    const html=renderField(value,{validate:true});
    assert.ok(inputTag(html).includes(`value="${value}"`));
    assert.doesNotMatch(inputTag(html),/\bmaxlength=/i);
    assertNoVisibleError(html);
  }
});

test('password and confirmation errors have independent accessible description ids',()=>{
  const html=renderToStaticMarkup(React.createElement(React.Fragment,null,
    React.createElement(PhonePasswordField,fieldProps(longPaste)),
    React.createElement(PhonePasswordField,fieldProps(longPaste,{
      label:'确认密码',error:confirmPhonePasswordError(longPaste,'123456'),
    })),
  ));
  const fields=html.match(/<div class="phone-password-field">[\s\S]*?<\/div>/g);
  assert.equal(fields?.length,2);
  assertVisibleError(fields[0],'密码最多支持 11 个字符');
  assertVisibleError(fields[1],'确认密码最多支持 11 个字符');
  const ids=fields.map(field=>inputTag(field).match(/aria-describedby="([^"]+)"/)[1]);
  assert.equal(new Set(ids).size,2,'Each input must describe its own error');
});
