import test from 'node:test';
import assert from 'node:assert/strict';
import {departmentOptions,departmentLabel,PUBLISHING_DEPARTMENTS} from '../public/review-native/publishing-departments.js';
import {editableContent,copyAsNewTask,hasUnsavedChanges} from '../public/review-native/task-workflow.js';
import {validateTask} from '../public/review-native/core.js';
import {memberRows,editMemberDepartment} from '../public/review-native/member-access.js';

test('departments are grouped and a legacy domain is not silently selected',()=>{
 assert.equal(PUBLISHING_DEPARTMENTS.length,19);
 assert.match(departmentOptions('开发部'),/<optgroup label="职能部门">/);
 assert.match(departmentOptions('开发部'),/<optgroup label="交付线部门">/);
 assert.match(departmentOptions('开发部'),/value="开发部" selected/);
 assert.equal(departmentLabel('产品开发'),'待补充部门');
 assert.match(departmentOptions('产品开发'),/value="" disabled selected/);
});
test('existing super and revoked members can edit department without identity or level inputs',()=>{
 for(const member of [{id:'super',name:'超级管理员',accessRole:'super_admin'},{id:'revoked',name:'已撤销成员',accessRole:'admin',status:'revoked'}]){
  assert.match(memberRows([member]),new RegExp(`data-member-department="${member.id}"`));
  let html='';
  editMemberDepartment({administrators:[member]},{isSuperAdmin:true,openModal:markup=>html=markup},member.id);
  assert.match(html,/保存部门/);
  assert.match(html,/name="department"/);
  assert.doesNotMatch(html,/name="(?:level|access_role)"/);
 }
 let opened=false;
 editMemberDepartment({administrators:[{id:'one'}]},{isSuperAdmin:false,toast:()=>{},openModal:()=>opened=true},'one');
 assert.equal(opened,false);
});
test('department-only changes are dirty and survive copying without rewriting the legacy domain',()=>{
 const task={domain:'数据交付',publishingDepartment:'IT部'};
 const changed={...task,publishingDepartment:'开发部'};
 assert.ok(hasUnsavedChanges(changed,task,{}));
 assert.equal(editableContent(changed).publishingDepartment,'开发部');
 assert.equal(copyAsNewTask(changed,{id:'new'}).domain,'数据交付');
 assert.equal(copyAsNewTask(changed,{id:'new'}).publishingDepartment,'开发部');
 assert.ok(validateTask(task).every(error=>!error.includes('请选择发布部门')));
 assert.ok(validateTask({...task,publishingDepartment:''}).includes('请选择发布部门'));
});
test('member list keeps real identity and actions while showing configured department separately',()=>{
 const html=memberRows([{id:'one',name:'成员',employee_no:'MCE01',departments:['飞书组织'],accessRole:'admin',certification:{domain:'产品开发',department:'IT部',level:'初级'}}]);
 assert.match(html,/<th>身份<\/th><th>部门<\/th><th>等级<\/th>/);
 assert.match(html,/<td>IT部<\/td>/);
 assert.match(html,/部门：飞书组织/);
 assert.match(html,/工号：MCE01/);
 assert.match(html,/data-member-edit="one"/);
});
