import test from 'node:test';
import assert from 'node:assert/strict';
import {memberRows,demoteMember} from '../public/review-native/member-access.js';

const owner={isSuperAdmin:true,canGrantSuperAdmins:true,currentUser:{id:'owner'}};
const people=[{id:'owner',name:'李鑫波',accessRole:'super_admin',protectedAdmin:true},
 {id:'second-owner',name:'刘默文',accessRole:'super_admin',protectedAdmin:true},
 {id:'super',name:'其他超级管理员',accessRole:'super_admin',protectedAdmin:false},
 {id:'ordinary',name:'普通管理员',accessRole:'admin',protectedAdmin:false}];

test('only highest-authority actor sees peer super demotion and revoke controls',()=>{
 const html=memberRows(people,owner);
 assert.match(html,/data-member-demote="super"/);
 assert.match(html,/data-member-revoke="super"/);
 for(const id of ['owner','second-owner'])assert.doesNotMatch(html,new RegExp(`data-member-(demote|revoke)="${id}"`));
 const peer=memberRows(people,{...owner,canGrantSuperAdmins:false,currentUser:{id:'super'}});
 assert.doesNotMatch(peer,/data-member-demote/);
 assert.doesNotMatch(peer,/data-member-revoke="super"/);
 assert.match(peer,/data-member-revoke="ordinary"/);
 assert.doesNotMatch(memberRows([{...people[2],protectedAdmin:undefined}],owner),/data-member-(demote|revoke)/);
});

test('revoked super can only be reauthorized by highest-authority actor',()=>{
 const members=[{...people[2],status:'revoked'}];
 assert.match(memberRows(members,owner),/data-member-restore="super"/);
 assert.doesNotMatch(memberRows(members,owner),/data-member-demote/);
 assert.doesNotMatch(memberRows(members,{...owner,canGrantSuperAdmins:false}),/data-member-restore/);
});

test('demotion confirmation lets owner select level and makes consequences clear',()=>{
 let html='';
 demoteMember({administrators:people},{...owner,openModal:value=>html=value},'super');
 assert.match(html,/确认降级/);
 assert.match(html,/name="level"/);
 for(const level of ['初级','中级','高级'])assert.ok(html.includes(level));
 assert.match(html,/重新登录后按普通管理员权限使用/);
 for(const id of ['owner','second-owner']){
  let opened=false;
  demoteMember({administrators:people},{...owner,openModal:()=>opened=true},id);
  assert.equal(opened,false);
 }
});
