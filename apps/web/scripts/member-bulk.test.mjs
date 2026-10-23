import test from 'node:test';
import assert from 'node:assert/strict';
import {filterBulkPeople,bulkRows,openBulkAccess,departmentRows,resolveBulkChoice} from '../public/review-native/member-bulk.js';

test('bulk list searches names, employee numbers, full departments and job titles',()=>{
 const people=[{name:'张三',employee_no:'MCE00001',departments:['开发部'],department_paths:['AI中心 / 开发部'],job_title:'高级助理'},{name:'李四',departments:['财务部'],job_title:'财务主管'}];
 assert.equal(filterBulkPeople(people,' mce00001 ')[0].name,'张三');
 assert.equal(filterBulkPeople(people,'AI中心')[0].name,'张三');
 assert.equal(filterBulkPeople(people,'助理')[0].name,'张三');
 assert.equal(filterBulkPeople(people,' 财务 ').length,1);
 assert.equal(filterBulkPeople(people,'王五').length,0);
 assert.equal(filterBulkPeople(people,'').length,2);
});

test('preview identity uses real employee numbers and escaped full department paths',()=>{
 const person={open_id:'ou_private_suffix',name:'<同名>',employee_no:'MCE00001',departments:['开发部'],department_paths:['AI中心 / 开发&部'],job_title:'经理',current_access:'未开通',action:'新增',status:'new'};
 const html=bulkRows([person],new Set([person.open_id]));
 assert.match(html,/class="bulk-member-details"><strong>&lt;同名&gt;<\/strong><div class="table-subtitle">工号：MCE00001<\/div><div class="table-subtitle">部门：AI中心 \/ 开发&amp;部<\/div>/);
 assert.ok(!html.includes('账号 ·'));
 assert.ok(!html.includes('选择 &lt;同名&gt; e_suffix'));
 const missing=bulkRows([{...person,employee_no:'',department_paths:[],departments:[]}],new Set());
 assert.ok(missing.includes('工号：未填写'));
 assert.ok(missing.includes('部门：未填写'));
});
test('only new candidates are selectable; existing/super/revoked cannot be selected',()=>{
 const people=['new','super','existing','revoked'].map(status=>({open_id:'ou_'+status,name:'<张三>',departments:['开发&部'],job_title:'经理',current_access:'已有权限',action:'保持不变',status}));
 const html=bulkRows(people,new Set(['ou_new']));
 assert.equal((html.match(/data-bulk-person=/g)||[]).length,1);
 assert.ok(html.includes('data-bulk-person="ou_new"'));
 assert.ok(html.includes('&lt;张三&gt;'));assert.ok(!html.includes('<张三>'));
 assert.ok(bulkRows(people,new Set(),true).includes('disabled'));
});
test('bulk entry rejects ordinary administrators',()=>{
 let opened=false,notice='';openBulkAccess({}, {isSuperAdmin:false,openModal:()=>opened=true,toast:s=>notice=s},()=>{});
 assert.equal(opened,false);assert.match(notice,/仅超级管理员/);
});

test('department controls show only roots, each with its own domain and entry level default',()=>{
 const html=departmentRows([{id:'a',name:'财务法务合规部',parent_id:'0',default_mode:'all'},
 {id:'b',name:'总经办',parent_id:'0',default_mode:'all'},
 {id:'child',name:'下级部门',parent_id:'b',default_mode:'off'}]);
 assert.equal((html.match(/data-bulk-domain/g)||[]).length,2);
 assert.equal((html.match(/data-bulk-level/g)||[]).length,2);
 assert.ok(!html.includes('下级部门'));
 assert.ok(html.indexOf('总经办')<html.indexOf('财务法务合规部'));
 assert.match(html,/<option>初级<\/option><option>中级<\/option><option>高级<\/option>/);
});

test('conflicts cannot be selected until an offered option is explicitly chosen',()=>{
 const person={open_id:'ou_conflict',name:'张三',departments:['开发部'],job_title:'经理',current_access:'未开通',action:'需要确认',status:'conflict',target:null,
 options:[{department_id:'a',department_name:'甲',domain:'技术开发',level:'高级'},{department_id:'b',department_name:'乙',domain:'PMO',level:'初级'}]};
 assert.ok(!bulkRows([person],new Set()).includes('data-bulk-person='));
 assert.ok(bulkRows([person],new Set()).includes('data-bulk-choice="ou_conflict"'));
 assert.equal(resolveBulkChoice(person,'unknown'),false);
 assert.equal(resolveBulkChoice(person,'b'),true);
 assert.equal(person.target.level,'初级');assert.equal(person.target.domain,'PMO');
 assert.ok(bulkRows([person],new Set()).includes('data-bulk-person='));
 assert.match(person.action,/PMO · 初级/);
 assert.equal(resolveBulkChoice(person,''),false);assert.equal(person.status,'conflict');
 person.status='existing';assert.equal(resolveBulkChoice(person,'a'),false);
});
