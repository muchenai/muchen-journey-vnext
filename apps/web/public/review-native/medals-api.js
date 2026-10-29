import {request} from './native-api.js?v=20261028-publication-local';
const toNative = {tech:'dev','ai-eval':'evaluation'};
const toServer = {dev:'tech',evaluation:'ai-eval'};
const native = row => ({...row,costs:(row.costs||[]).map(c=>({...c,badgeId:toNative[c.badgeId]||c.badgeId}))});
export function createMedalsApi(store) {
  let medals=[], redemptions=[];
  const api = {
    loading:false, error:'',
    isAdmin:()=>!!store.capabilities?.canPublish,
    async refresh() {
      api.loading=true;api.error='';
      try {const data=await request({command:'medalCatalog'});medals=data.medals.map(native);redemptions=data.redemptions.map(native);}
      catch(error){api.error=error.message;throw error;}
      finally{api.loading=false;}
    },
    listMedals({query='',status='all'}={}) {const q=query.trim().toLowerCase();return structuredClone(medals.filter(m=>(status==='all'||m.status===status)&&(!q||`${m.name} ${m.description}`.toLowerCase().includes(q))));},
    getMedal:id=>structuredClone(medals.find(m=>m.id===id)||null),
    listRedemptions({query=''}={}){const q=query.trim().toLowerCase();return structuredClone(redemptions.filter(r=>!q||`${r.medalName} ${r.studentName} ${r.studentId}`.toLowerCase().includes(q)));},
    getStats:()=>({total:medals.length,published:medals.filter(m=>m.status==='published').length,draft:medals.filter(m=>m.status==='draft').length,redemptions:redemptions.length}),
    async saveMedal(medal) {
      const id=medal.id||crypto.randomUUID();
      const payload={expected_revision:medal.revision||0,content:{...medal,costs:medal.costs.map(c=>({...c,badgeId:toServer[c.badgeId]||c.badgeId}))}};
      const saved=native(await request({command:'saveMedal',id,payload}));
      medals=[saved,...medals.filter(m=>m.id!==id)];
      return saved;
    },
    async setMedalStatus(id,status) {const medal=api.getMedal(id);if(!medal)throw new Error('徽章不存在，请刷新。');return api.saveMedal({...medal,status});},
  };
  return api;
}
