import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import {medalArtwork, shopArtworkPaths} from '../public/review-native/medal-artwork.js';
import * as artworks from '../public/review-native/badge-artworks.js';
import * as layouts from '../public/review-native/badge-artwork-layout.js';

const root = new URL('../', import.meta.url);
const nativeRequire = createRequire(import.meta.url);
const catalogData = JSON.parse(readFileSync(new URL('src/app/project29/badgeCatalogData.json', root), 'utf8'));
function load(name, dependencies = {}) {
  const text = readFileSync(new URL('src/app/project29/' + name, root), 'utf8');
  const source = ts.transpileModule(text, {compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022, esModuleInterop:true}}).outputText;
  const compiledModule = {exports:{}};
  vm.runInNewContext(source, {module:compiledModule, exports:compiledModule.exports, require:name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name)});
  return compiledModule.exports;
}
const artwork = load('badgeArtwork.ts', {'./badgeCatalogData.json':catalogData});
const catalog = load('badgeCatalog.ts', {'./badgeCatalogData.json':catalogData, './badgeArtwork':artwork});
const economy = load('badgeEconomy.ts');
const records = [
  ['洞察新星','product-1','blue',[['product',20],['data',10]]],
  ['代码构筑者','tech-1','purple',[['tech',35]]],
  ['数据领航员','data-3','blue',[['data',50],['product',10]]],
  ['协作指挥官','pmo-2','purple',[['pmo',65],['project',10]]],
  ['智能探索家','ai-evaluation-2','gold',[['ai-eval',90],['ai',20]]],
  ['品质守护者','quality-1','gold',[['quality',180]]],
].map(([name,artworkId,style,costs], i) => ({id:`real-${i}`,name,artworkId,style,description:'',image:'',revision:1,stock:null,costs:costs.map(([badgeId,points])=>({badgeId,points}))}));

test('only six actual publications connect to the 87-artwork catalog; none are granted by importing products',()=>{
  const {badges,wallet} = economy.adaptMedals({medals:records, redemptions:[], wallet:{badgeBalances:{}}});
  assert.equal(badges.length,6);
  assert.equal(wallet.owned.length,0);
  const linked = catalog.connectBadgeCatalog(badges,wallet.owned);
  assert.equal(linked.filter(m=>m.publication?.published).length,6);
  assert.equal(linked.filter(m=>!m.publication).length,81);
  assert.ok(linked.every(m=>catalog.catalogDisplayLevel(m,wallet.owned) === 0));
  assert.ok(badges.every(m=>!economy.badgeCostStatus(wallet,m).affordable));
});

test('learner and administrator use the same original artwork and grade',()=>{
  const {badges} = economy.adaptMedals({medals:records, redemptions:[], wallet:{badgeBalances:{}}});
  assert.equal(Object.keys(shopArtworkPaths).length,6);
  for(let i=0;i<records.length;i++){
    const admin = medalArtwork(records[i]), learner = artwork.badgeArtworkFor(badges[i]);
    assert.equal(admin.symbol,`/assets/journey-badges/centered-icons/${learner.path}.webp`);
    assert.equal(admin.frame,`/assets/journey-badges/frames/level-${learner.level}.svg`);
    assert.ok(existsSync(new URL('public'+admin.symbol,root)));
    assert.ok(existsSync(new URL('public'+admin.frame,root)));
  }
  assert.equal(artwork.badgeArtworkFor(badges[1]).level,2);
  assert.equal(artwork.badgeArtworkFor(badges[4]).level,3);
  assert.equal(medalArtwork({artworkId:'__proto__',style:'purple'}),null);
});

test('multi-type affordability uses each real balance and retains ownership/art after delisting',()=>{
  const data={medals:records,wallet:{badgeBalances:{product:40,data:9}},redemptions:[]};
  let {badges,wallet}=economy.adaptMedals(data);
  assert.equal(economy.badgeCostStatus(wallet,badges[0]).affordable,false);
  data.wallet.badgeBalances.data=10;
  ({badges,wallet}=economy.adaptMedals(data));
  assert.equal(economy.badgeCostStatus(wallet,badges[0]).affordable,true);
  data.redemptions=[{...records[1],id:'receipt',medalId:records[1].id,medalName:records[1].name,redeemedAt:'2026-11-02T00:00:00Z'}];
  data.medals=records.filter(m=>m.id!==records[1].id);
  ({badges,wallet}=economy.adaptMedals(data));
  const owned=badges.find(m=>m.id===records[1].id);
  assert.equal(owned.published,false);
  assert.equal(artwork.badgeArtworkFor(owned).level,2);
  assert.equal(wallet.history[0].costs[0].amount,35);
  const linked=catalog.connectBadgeCatalog(badges,wallet.owned).find(m=>m.artwork.id==='tech-1');
  assert.equal(catalog.catalogDisplayLevel(linked,wallet.owned),2);
});

test('native admin renders actual artwork in catalog and redemption history',()=>{
  const source=readFileSync(new URL('public/review-native/medals.js',root),'utf8').replace(/^import .+;\r?\n/gm,'').replace('export function createMedalsController','function createMedalsController');
  const context={...artworks,...layouts,structuredClone,BADGES:[],e:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),normalizeBadgeImage:()=>'',readBadgeImage(){},svgToBadgeImage(){}};
  vm.runInNewContext(source+'\nthis.create = createMedalsController;',context);
  const controller=context.create({economy:{isAdmin:()=>true,getStats:()=>({total:6,published:6,draft:0,redemptions:0}),listMedals:()=>records.map(m=>({...m,status:'published'})),listRedemptions:()=>[]},ui:{icon:()=>'',refresh(){}}});
  const html=controller.render();
  assert.equal((html.match(/md-art-builtin/g)||[]).length,6);
  assert.equal((html.match(/level-2.svg/g)||[]).length,2);
  assert.ok(html.includes('洞察新星') && html.includes('品质守护者'));
});
