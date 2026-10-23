import test from 'node:test';
import assert from 'node:assert/strict';
import {memberRows,searchRows,openCertification,grantRoleOptions,directoryStatusText,filterAdministrators} from '../public/review-native/member-access.js';

test('company results show name, real employee number, title and full department path safely',()=>{
 const html=searchRows([{open_id:'ou_aaaaaaaa',name:'同名<script>',employee_no:'MCE00001',job_title:'经理<主管>',department_paths:['中心 / 研发<部>'],departments:['研发<部>'],avatar:'javascript:alert(1)'},{open_id:'ou_bbbbbbbb',name:'同名<script>',employee_no:'MCE00002',departments:['产品'],avatar:''}]);
 assert.ok(html.includes('MCE00001')&&html.includes('MCE00002'));
 assert.ok(!html.includes('aaaaaaaa')&&!html.includes('bbbbbbbb'));
 assert.ok(html.includes('部门：中心 / 研发&lt;部&gt;'));
 assert.ok(html.includes('职务：经理&lt;主管&gt;'));
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('javascript:'));
 const name=html.indexOf('<strong>'),number=html.indexOf('工号：'),title=html.indexOf('职务：'),department=html.indexOf('部门：');
 assert.ok(name<number&&number<title&&title<department);
});

test('missing employee data stays empty rather than substituting an account ID',()=>{
 const html=searchRows([{open_id:'ou_not_an_employee_number',name:'测试'}]);
 assert.ok(html.includes('工号：未填写')&&html.includes('职务：未填写')&&html.includes('部门：未填写'));
 assert.ok(!html.includes('ou_not_an_employee_number'));
});

test('only ordinary administrators have revoke controls; revoked entries support reauthorization',()=>{
 const html=memberRows([{id:'super-12345678',name:'超级管理员',accessRole:'super_admin',status:'active'},{id:'admin-12345678',name:'普通管理员',accessRole:'admin',status:'active',certification:{level:'中级'}},{id:'revoked-12345678',name:'已撤销',accessRole:'admin',status:'revoked'}]);
 assert.ok(!html.includes('data-member-revoke="super-12345678"'));
 assert.ok(html.includes('data-member-revoke="admin-12345678"'));
 assert.ok(html.includes('data-member-restore="revoked-12345678"'));
 assert.ok(html.includes('入门、进阶'));
});
test('ordinary administrators cannot open the certification modal',()=>{
 let opened=false,notice='';openCertification({}, {isSuperAdmin:false,toast:m=>notice=m,openModal:()=>opened=true});
 assert.equal(opened,false);assert.match(notice,/仅超级管理员/);
});

test('administrator identities show real numbers and paths while preserving role and safe markup',()=>{
 const people=[{id:'internal-id',name:'同名<管理员>',employee_no:'MCE00004',department_paths:['平台 / 开发&部'],accessRole:'super_admin'},
   {id:'other-id',name:'同名<管理员>',employee_no:'MCE00005',departments:['财务部'],status:'revoked'}];
 assert.deepEqual(filterAdministrators(people,' mce00004 '),[people[0]]);
 assert.equal(filterAdministrators(people,'同名').length,2);
 assert.equal(filterAdministrators(people,'00005')[0].status,'revoked');
 assert.equal(filterAdministrators([{id:'missing',name:'缺失'}],'missing').length,0);
 const html=memberRows(people);
 assert.ok(html.includes('工号：MCE00004')&&html.includes('部门：平台 / 开发&amp;部'));
 assert.ok(html.includes('超级管理员')&&html.includes('同名&lt;管理员&gt;'));
 assert.ok(!html.includes(' · ernal-id'));
 assert.ok(html.indexOf('同名&lt;管理员&gt;')<html.indexOf('工号：MCE00004'));
 const missing=memberRows([{id:'missing',name:'缺失',accessRole:'super_admin'}]);
 assert.ok(missing.includes('工号：未填写')&&missing.includes('部门：未填写'));
});

test('only privileged super administrators see the super grant option',()=>{
 assert.match(grantRoleOptions(true),/value="admin">普通管理员/);
 assert.match(grantRoleOptions(true),/value="super_admin">超级管理员/);
 assert.equal(grantRoleOptions(false),'<option value="admin">普通管理员</option>');
 assert.equal(grantRoleOptions(undefined),grantRoleOptions(false));
});

test('certification form uses server capability rather than display name',()=>{
 for(const [name,privileged] of [['刘默文',false],['李鑫波',false],['账号已改名',true]]){
  let html='';openCertification({}, {isSuperAdmin:true,canGrantSuperAdmins:privileged,
    currentUser:{name},openModal:markup=>html=markup});
  assert.equal(html.includes('value="super_admin"'),privileged);
  assert.ok(html.includes('name="access_role"'));
 }
});


test('directory status distinguishes preparation, stale snapshots and background refresh',()=>{
 assert.match(directoryStatusText({ready:false}),/正在准备/);
 assert.match(directoryStatusText({ready:false,error_code:'FAILED'}),/首次同步失败/);
 const base={ready:true,last_updated_at:'2026-10-23T02:00:00Z'};
 assert.match(directoryStatusText(base),/每天凌晨 3 点自动更新（北京时间）/);
 assert.match(directoryStatusText({...base,syncing:true}),/可继续搜索/);
 assert.match(directoryStatusText({...base,error_code:'DIRECTORY_UNAVAILABLE'}),/暂用已有名单/);
 assert.match(directoryStatusText({...base,error_code:'DIRECTORY_PERMISSION_REQUIRED'}),/权限已变化/);
});
