import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const nativeRequire=createRequire(import.meta.url);
const root=new URL('../',import.meta.url);
const json=name=>JSON.parse(readFileSync(new URL('src/app/project29/'+name,root),'utf8'));
function load(name,deps={}) {
 const source=readFileSync(new URL('src/app/project29/'+name,root),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
 const compiledModule={exports:{}};
 vm.runInNewContext(code,{module:compiledModule,exports:compiledModule.exports,require:key=>Object.hasOwn(deps,key)?deps[key]:nativeRequire(key)});
 return compiledModule.exports;
}
const data=json('badgeCatalogData.json');
const artwork=load('badgeArtwork.ts',{'./badgeCatalogData.json':data});
const catalog=load('badgeCatalog.ts',{'./badgeCatalogData.json':data,'./badgeArtwork':artwork});
const economy=load('badgeEconomy.ts');
const bridges=load('world-map-loading.ts');
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('all 87 original artworks, 29 categories and four frames exist locally',()=>{
 assert.equal(data.length,87);assert.equal(catalog.badgeCatalogCategories.length,29);
 assert.equal(new Set(data.map(item=>item.id)).size,87);
 for(const item of data)assert.ok(existsSync(new URL(`public/assets/journey-badges/centered-icons/${item.path}.webp`,root)));
 for(const level of ['locked','level-1','level-2','level-3'])assert.ok(existsSync(new URL(`public/assets/journey-badges/frames/${level}.svg`,root)));
 assert.equal(catalog.filterBadgeCatalog('points').length,54);
 assert.equal(catalog.filterBadgeCatalog('delivery').length,21);
 assert.equal(catalog.filterBadgeCatalog('general').length,12);
 assert.equal(catalog.filterBadgeCatalog('all',data[0].categoryId).length,3);
 assert.ok(catalog.filterBadgeCatalog('all','all',data[0].name).some(e=>e.artwork.id===data[0].id));
});

test('catalog never grants demo ownership or associates publications by name, category or order',()=>{
 const badge={id:'real-id',name:data[0].name,category:data[0].categoryName,tone:'gold',image:'',published:true};
 const unbound=catalog.connectBadgeCatalog([badge],['real-id']);
 assert.equal(unbound.filter(e=>e.publication).length,0);
 assert.ok(unbound.every(e=>catalog.catalogDisplayLevel(e,['real-id'])===0));
 for(const [tone,level] of [['cyan',1],['violet',2],['gold',3]]){
   const bound=catalog.connectBadgeCatalog([{...badge,artworkId:data[0].id,tone}],['real-id'])[0];
   assert.equal(catalog.catalogDisplayLevel(bound,[]),0);
   assert.equal(catalog.catalogDisplayLevel(bound,['real-id']),level);
 }
 assert.equal(artwork.badgeArtworkFor({...badge,artworkId:'../../bad'}),null);
});

test('real balances, owned delisted medals and redemption costs survive catalog adaptation',()=>{
 const response={medals:[],wallet:{badgeBalances:{product:23,data:11}},redemptions:[{id:'receipt',medalId:'real-owned',medalName:'保留的真实徽章',image:'data:image/png;base64,AA==',style:'gold',costs:[{badgeId:'product',points:7}],redeemedAt:'2026-11-02T00:00:00Z'}]};
 const original=JSON.stringify(response), adapted=economy.adaptMedals(response);
 assert.equal(adapted.wallet.balances['产品开发'],23);
 assert.equal(adapted.wallet.owned[0],'real-owned');
 assert.equal(adapted.wallet.history[0].costs[0].amount,7);
 assert.equal(adapted.badges[0].published,false);
 assert.equal(adapted.badges[0].image,response.redemptions[0].image);
 catalog.connectBadgeCatalog(adapted.badges,adapted.wallet.owned);
 assert.equal(JSON.stringify(response),original);
});

test('hidden map waits for decoding and fonts without depending on suspended animation frames',async()=>{
 let imageDone,fontDone;const sent=[];
 const image={complete:true,naturalWidth:100,decode:()=>new Promise(resolve=>{imageDone=resolve})};
 const document={body:{},images:[image],querySelector:()=>({}),fonts:{ready:new Promise(resolve=>{fontDone=resolve})}};
 vm.runInNewContext(bridges.worldMapReadyBridge,{document,parent:{postMessage:m=>sent.push(m)},requestAnimationFrame(){throw Error('hidden iframe frames are suspended')},MutationObserver:class{observe(){}disconnect(){}}});
 await flush();assert.equal(sent.length,0);
 imageDone();await flush();assert.equal(sent.length,0);
 fontDone();await flush();assert.equal(sent[0].type,'journey-world-map-ready');
});

test('failed map image reports an error instead of revealing an incomplete scene',async()=>{
 const sent=[];
 vm.runInNewContext(bridges.worldMapReadyBridge,{document:{body:{},images:[{complete:true,naturalWidth:0}],querySelector:()=>({}),fonts:{ready:Promise.resolve()}},parent:{postMessage:m=>sent.push(m)},requestAnimationFrame(){throw Error('must not reveal')},MutationObserver:class{observe(){}disconnect(){}}});
 await flush();assert.equal(sent[0].type,'journey-world-map-error');
});

test('login preload includes every map bitmap',()=>{
 const preload=json('preloadAssets.json');
 const html=readFileSync(new URL('public/world-map/index.html',root),'utf8');
 const urls=[...new Set(html.match(/\/world-map\/[a-f0-9]+\.webp/g))];
 assert.equal(urls.length,16);
 for(const url of urls)assert.ok(preload.includes(url),url);
});
