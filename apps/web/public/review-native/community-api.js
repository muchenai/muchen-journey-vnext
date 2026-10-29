import {request} from './native-api.js?v=20261028-publication-local';

export function createCommunityApi(module,getCurrentUser,empty) {
 let cache={...structuredClone(empty),revision:0};
 const isAdmin=()=>['admin','super_admin'].includes(getCurrentUser()?.accessRole);
 const owner=()=>{const id=getCurrentUser()?.id;if(!id||!isAdmin())throw new Error('仅管理员可使用此模块。');return id;};
 async function send(action,payload={},revision){
  const actor=owner();
  const value=await request({command:module,payload:{action,payload,...(revision===undefined?{}:{expected_revision:revision})}});
  if(actor!==owner())throw new Error('登录身份已改变，请刷新页面。');
  if(value.snapshot)cache=value.snapshot;
  return value;
 }
 return {isAdmin,snapshot:()=>structuredClone(cache),
  ready:async()=>{await send('snapshot');return structuredClone(cache);},
  raw:async(action,payload)=>(await send(action,payload)).result,
  async change(action,payload){
   try{return (await send(action,payload,cache.revision)).result;}
   catch(error){await send('snapshot').catch(()=>{});throw error;}
  }
 };
}
