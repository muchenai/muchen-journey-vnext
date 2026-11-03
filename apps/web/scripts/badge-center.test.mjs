import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import test from 'node:test';
import {createMedalsController} from '../public/review-native/medals.js';
import {BADGE_ARTWORKS, BADGE_ARTWORK_CATEGORIES, RECOMMENDED_DELIVERY_ARTWORKS} from '../public/review-native/badge-artworks.js';
import {BADGE_ARTWORK_FRAMES, BADGE_ARTWORK_LAYOUTS} from '../public/review-native/badge-artwork-layout.js';

const economy = {isAdmin:()=>true,getStats:()=>({total:0,published:0,draft:0,redemptions:0}),listMedals:()=>[],listRedemptions:()=>[]};
const ui = {icon:()=>'',refresh(){}};
const make = () => createMedalsController({economy,ui});
test('every artwork uses the reference bounds without CSP-blocked inline styles',()=>{
  const css=readFileSync(new URL('../public/review-native/badge-artwork-layout.css',import.meta.url),'utf8');
  const html=readFileSync(new URL('../public/review-native/index.html',import.meta.url),'utf8');
  assert.ok(html.includes('./badge-artwork-layout.css?v=20261103-badge-layout-fix'));
  for(const item of BADGE_ARTWORKS){
    const layout=BADGE_ARTWORK_LAYOUTS[item.id];
    const rule=`.md-badge-composite[data-artwork="${item.id}"] > .md-badge-symbol { left: ${layout.left}%; top: ${layout.top}%; width: ${layout.width}%; height: ${layout.height}%; }`;
    assert.ok(css.includes(rule),item.id);
    assert.ok(layout.width>0 && layout.width<100 && layout.height>0 && layout.height<100);
  }
  const controller=make(); controller.selectTab('artworks');
  const gallery=controller.render();
  assert.ok(!gallery.includes('style='));
  assert.equal((gallery.match(/data-artwork=/g)||[]).length,28);
});
test('all administrator artwork IDs, metadata and assets match the learner and API libraries',()=>{
  const learner=JSON.parse(readFileSync(new URL('../src/app/project29/badgeCatalogData.json',import.meta.url)));
  const api=JSON.parse(readFileSync(new URL('../../api/journey_api/badge_artworks.json',import.meta.url)));
  assert.equal(BADGE_ARTWORKS.length,87);
  assert.equal(BADGE_ARTWORK_CATEGORIES.length,29);
  for(const item of BADGE_ARTWORKS){
    const metadata=api.find(a=>a.id===item.id), peer=learner.find(a=>a.id===item.id);
    assert.ok(metadata && peer && BADGE_ARTWORK_LAYOUTS[item.id]);
    assert.equal(metadata.path,peer.path);
    assert.equal(metadata.categoryId,item.categoryId);
    assert.ok(existsSync(new URL('../public'+item.inner,import.meta.url)));
  }
  for(const frame of BADGE_ARTWORK_FRAMES)assert.ok(existsSync(new URL('../public'+frame,import.meta.url)));
});
test('the reference opens with seven recommended delivery artworks and four states each',()=>{
  const controller=make(); controller.selectTab('artworks');
  const html=controller.render();
  assert.equal((html.match(/<article class="md-artwork-card"/g)||[]).length,7);
  assert.equal((html.match(/<figure /g)||[]).length,28);
  for(const id of RECOMMENDED_DELIVERY_ARTWORKS)assert.ok(html.includes('data-md-artwork-use="'+id+'"'));
  for(const name of ['图标素材','专业能力','通用成长','搜索图标名称或类别','未解锁','一级','二级','三级'])assert.ok(html.includes(name));
});
test('gallery selection fills an editable real draft and keeps all three tabs accessible',()=>{
  const controller=make(); controller.selectTab('artworks');
  const results={addEventListener(type,handler){this[type]=handler;}};
  const page={querySelectorAll:()=>[],querySelector:selector=>selector==='[data-md-artwork-results]'?results:null};
  controller.bind({querySelector:()=>page});
  results.click({target:{closest:()=>({dataset:{mdArtworkUse:'delivery-agent-1'}})}});
  const html=controller.render();
  assert.ok(html.includes('新增徽章') && html.includes('value="轨迹编织者"'));
  assert.ok(html.includes('data-md-level="2"') && html.includes('data-md-level="3"'));
  assert.ok(html.includes('保存并上架') && html.includes('兑换点数'));
  controller.reset();
  for(const tab of ['catalog','artworks','records']){controller.selectTab(tab);assert.ok(controller.render().includes('data-md-tab="'+tab+'"'));}
});
