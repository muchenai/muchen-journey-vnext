import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { openCertificationCenter } from '../public/review-native/certification-center.js';
import { canSaveIssuers, issuerHistory, issuerSearchRows, issuerWarning } from '../public/review-native/experience-permissions.js';
import { searchRows } from '../public/review-native/member-access.js';

const person = (id, hasManagementAccess = true) => ({ id, openId:'ou_'+id, name:'张三', hasManagementAccess });

test('issuer results render the same directory profile card as member certification', () => {
  const member = { name:'张三', avatar:'https://example.com/a.png', employee_no:'M001',
    job_title:'AI 应用工程师', department_paths:['平台中心 / 开发部'], departments:['开发部'] };
  const issuer = { name:member.name, avatar:member.avatar, employeeNo:member.employee_no,
    jobTitle:member.job_title, departmentPaths:member.department_paths, departments:member.departments };
  assert.equal(issuerSearchRows([issuer]),searchRows([member]));
  assert.equal(issuerSearchRows([]),searchRows([]));
});

test('both distinct selected identities must currently have management access, irrespective of matching names', () => {
  assert.equal(canSaveIssuers([person('1'),person('2')]),true);
  assert.equal(canSaveIssuers([person('1'),null]),true);
  assert.equal(canSaveIssuers([null,null]),true);
  for (const selections of [[],[person('1'),person('1')],[person('1'),person('2',false)],[person(null),person('2')]]) {
    assert.equal(canSaveIssuers(selections),false);
  }
  assert.equal(issuerWarning(person(null,false)), '「张三」尚未开通管理系统访问权限。请先在「成员认证」中为其开通权限');
  assert.equal(issuerWarning(person('1')), '');
  assert.equal(issuerWarning(undefined),'');
});

test('the experience permission tab follows the server permission independent of ordinary super admin or issuer access', () => {
  function html(rights) {
    let result='';
    openCertificationCenter({}, {...rights,openModal:markup=>{result=markup;}}, {preferred:'experience'});
    return result;
  }
  assert.match(html({isSuperAdmin:true,canConfigureExperience:true}), /data-cert-tab="experience"/);
  for (const rights of [{},{isSuperAdmin:true},{canGrantExperience:true},{isSuperAdmin:true,canGrantExperience:true}]) {
    assert.doesNotMatch(html(rights), /data-cert-tab="experience"/);
    assert.doesNotMatch(html(rights), /data-cert-tab="courses"|课程人员与权限/);
  }
});

test('permission history shows the operator, slot and previous and next assignee safely', () => {
  assert.match(issuerHistory([]), /暂无权限变更记录/);
  const html = issuerHistory([{time:'2026-11-27T00:00:00Z', operatorName:'<张>', slot:2, beforeName:null, afterName:'李四'}]);
  assert.match(html, /&lt;张&gt;/);
  assert.match(html, /发放管理员 2/);
  assert.match(html, /未指定<\/td><td>李四/);
});

test('opening an experience deep link uses the server capabilities before constructing the workspace or opening a demo', () => {
  const entry = readFileSync(new URL('../public/review-native/app.js',import.meta.url),'utf8');
  const code = entry.slice(entry.indexOf('function initialPage()'),entry.indexOf('let page = initialPage();'));
  function initial(capabilities) {
    const location=new URL('http://localhost:3000/review?demo=single#experience');
    const history={replaceState:(_state,_title,url)=>{location.href=url.href;}};
    const store={capabilities,data:{draft:{id:'d'}},getTask:()=>null};
    const result=vm.runInNewContext(code+'\ninitialPage()', {location,history,URL,store,legacyTaskPage:'publish/saved-task',villagePublishPage:'publish/village-courses'});
    return {result,location};
  }
  for(const caps of [{},{isSuperAdmin:true,canConfigureExperience:true},{canGrantExperience:false}]) {
    const {result,location}=initial(caps);
    assert.equal(result,'review');
    assert.equal(location.hash,'#review');
    assert.equal(location.searchParams.has('demo'),false);
  }
  assert.equal(initial({canGrantExperience:true}).result,'experience');
});
