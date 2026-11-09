import {createCommunityApi} from './community-api.js?v=20261028-server';
export const GUILD_CAPABILITIES = Object.freeze([
  { id: 'data', name: '数据交付' },
  { id: 'implementation', name: '交付实施' },
  { id: 'quality', name: '质量验收' },
  { id: 'communication', name: '客户沟通' },
  { id: 'collaboration', name: '项目协作' },
]);
export const GUILD_LEVELS = Object.freeze(['初级', '中级', '高级']);

export function createGuildRequestApi({getCurrentUser,fetcher=(...args)=>fetch(...args)}) {
 let cache={requests:[]},cacheOwner='',loaded=false,error='',loading=false,refreshPromise=null;
 const reviewing=new Set();
 const isAdmin=()=>['admin','super_admin'].includes(getCurrentUser()?.accessRole);
 const actor=()=>{const id=getCurrentUser()?.id;if(!id||!isAdmin())throw new Error('仅管理员可审核公会晋级申请。');return id;};
 function clear(){cache={requests:[]};cacheOwner='';loaded=false;error='';}
 function snapshot(){if(cacheOwner&&getCurrentUser()?.id!==cacheOwner)clear();return structuredClone(cache);}
 async function send(method,body){
  const owner=actor();
  const response=await fetcher('/api/review-native/guild-requests',{method,credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:undefined,...(body?{body:JSON.stringify(body)}:{})});
  if(owner!==getCurrentUser()?.id||!isAdmin()){clear();throw new Error('登录身份已改变，请刷新页面。');}
  let result;try{result=await response.json();}catch{throw new Error('晋级审核数据读取失败，请重试。');}
  if(!response.ok||result?.ok===false)throw new Error(typeof result?.error==='string'?result.error:result?.error?.message||'晋级审核操作失败，请重试。');
  const value=result?.ok===true?result.data:result;
  if(!value||!Array.isArray(value.requests))throw new Error('晋级审核数据格式异常，请重新加载。');
  cache=structuredClone(value);cacheOwner=owner;loaded=true;error='';
  return snapshot();
 }
 async function refresh(){
  snapshot();if(refreshPromise)return refreshPromise;if(reviewing.size)return snapshot();
  loading=true;error='';
  refreshPromise=send('GET').catch(err=>{error=err.message;throw err;}).finally(()=>{loading=false;refreshPromise=null;});
  return refreshPromise;
 }
 return {
  snapshot,refresh,currentUserId:()=>getCurrentUser()?.id,
  get loaded(){snapshot();return loaded;},get loading(){return loading;},get error(){snapshot();return error;},
  async review(id,decision,reason=''){
   const owner=actor();
   if(refreshPromise)await refreshPromise;
   if(!loaded||cacheOwner!==owner)throw new Error('登录身份或审核列表已变化，请重新加载。');
   const item=cache.requests.find(row=>row.id===id);
   if(!item||item.status!=='pending')throw new Error('此申请已处理或不存在，请重新加载。');
   if(item.studentId===owner)throw new Error('不能审核自己的晋级申请，请由其他管理员处理。');
   if(reviewing.size)throw new Error('已有申请正在提交审核，请稍候。');
   reason=String(reason||'').trim();
   if(!['approved','returned'].includes(decision)||reason.length>1000)throw new Error('审核参数无效。');
   if(decision==='returned'&&!reason)throw new Error('请填写退回原因。');
   reviewing.add(id);
   try{return await send('POST',{id,decision,reason});}
   catch(err){reviewing.delete(id);if(owner===getCurrentUser()?.id&&isAdmin())await refresh().catch(()=>{});else clear();throw err;}
   finally{reviewing.delete(id);}
  },
 };
}

export function createGuildStore({getCurrentUser,fetcher}) {
 const api=createCommunityApi('guild',getCurrentUser,{learners:[],tasks:[],certifications:[],labs:[],rules:[],contributions:[],stats:{certifiedLearners:0,publishedLabs:0,totalPoints:0}});
 const reviews=createGuildRequestApi({getCurrentUser,fetcher});
 return {...api,ready:async()=>{const [result]=await Promise.all([api.ready(),reviews.refresh().catch(()=>null)]);return result;},
  requestSnapshot:reviews.snapshot,refreshRequests:reviews.refresh,reviewRequest:reviews.review,currentUserId:reviews.currentUserId,
  get requestsLoaded(){return reviews.loaded;},get requestsLoading(){return reviews.loading;},get requestsError(){return reviews.error;},
  grantCertification:p=>api.change('grantCertification',p),revokeCertification:(id,reason)=>api.change('revokeCertification',{id,reason}),saveLab:p=>api.change('saveLab',p),setLabStatus:(id,status)=>api.change('setLabStatus',{id,status}),saveRule:p=>api.change('saveRule',p),setRuleEnabled:(id,enabled)=>api.change('setRuleEnabled',{id,enabled})};
}
