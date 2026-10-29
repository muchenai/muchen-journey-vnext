import {createCommunityApi} from './community-api.js?v=20261028-server';
export const GUILD_CAPABILITIES = Object.freeze([
  { id: 'data', name: '数据交付' },
  { id: 'implementation', name: '交付实施' },
  { id: 'quality', name: '质量验收' },
  { id: 'communication', name: '客户沟通' },
  { id: 'collaboration', name: '项目协作' },
]);
export const GUILD_LEVELS = Object.freeze(['初级', '中级', '高级']);

export function createGuildStore({getCurrentUser}) {
 const api=createCommunityApi('guild',getCurrentUser,{learners:[],tasks:[],certifications:[],labs:[],rules:[],contributions:[],stats:{certifiedLearners:0,publishedLabs:0,totalPoints:0}});
 return {...api,grantCertification:p=>api.change('grantCertification',p),revokeCertification:(id,reason)=>api.change('revokeCertification',{id,reason}),saveLab:p=>api.change('saveLab',p),setLabStatus:(id,status)=>api.change('setLabStatus',{id,status}),saveRule:p=>api.change('saveRule',p),setRuleEnabled:(id,enabled)=>api.change('setRuleEnabled',{id,enabled})};
}
