import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const nativeRequire = createRequire(import.meta.url);
function load(file, deps = {}, globals = {}, extra = '') {
  const source = readFileSync(new URL('../src/app/' + file, import.meta.url), 'utf8') + extra;
  const code = ts.transpileModule(source, {compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop:true,
  }}).outputText;
  const compiledModule = {exports:{}};
  vm.runInNewContext(code, {module:compiledModule, exports:compiledModule.exports, URL, Response, ...globals,
    require:name => Object.hasOwn(deps, name) ? deps[name] : nativeRequire(name)});
  return compiledModule.exports;
}
const economy = load('project29/badgeEconomy.ts');
const departments = load('project29/taskDepartments.ts', {'./badgeEconomy':economy});
const navigation = load('project29/world-map-navigation.ts', {'./taskDepartments':departments});

test('map departments map by publishing department; delivery selects all seven lines', () => {
  for (const department of departments.taskDepartments.filter(item => !item.delivery)) {
    assert.equal(navigation.worldMapTaskDepartment(department.name), department.id);
  }
  assert.equal(navigation.worldMapTaskDepartment('交付线'), 'delivery');
  for (const bad of [null, {}, '产品开发', 'delivery', 'https://elsewhere.test']) {
    assert.equal(navigation.worldMapTaskDepartment(bad), null);
  }
  const tasks = departments.taskDepartments.map(item => ({publishingDepartment:item.name}));
  assert.equal(tasks.filter(task => departments.belongsToDepartment(task, navigation.worldMapTaskDepartment('交付线'))).length, 7);
});

test('only the village map response adds task navigation; original close/geometry/CSP remain', async () => {
  const original = '<html><head></head><body><aside class="planet-detail"><h2 id="planet-detail-title">财务法务合规部</h2><button class="detail-return">返回地图</button><button class="detail-close">×</button></aside></body></html>';
  const route = load('api/learner/world-map/route.ts', {
    'node:fs/promises':{readFile:async()=>original},
    '@/app/project29/world-map-navigation':navigation,
    '@/app/project29/world-map-loading':load('project29/world-map-loading.ts'),
  }, {process:{cwd:()=>'/app'}});
  for (const query of ['', '?tasks=academy', '?tasks=guild', '?tasks=dashboard', '?tasks=village']) {
    const response = await route.GET(new Request('http://localhost/api/learner/world-map' + query));
    const html = await response.text();
    assert.equal(html.includes('journey-world-map-tasks'), query === '?tasks=village');
    assert.match(html, /class="detail-close">×/);
    assert.match(html, /返回地图/);
    assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'self'/);
    if (query === '?tasks=village') assert.match(html, /<script nonce="[^"]+">\(\(\)=>\{\s+const selector='\.planet-detail \.detail-return'/);
  }
});

test('map task button exits fullscreen then notifies parent; close button is not intercepted', async () => {
  const listeners = {}, sent = [], order = [];
  let observer;
  const button = {textContent:'返回地图'};
  class Element { constructor(matches) { this.matches = matches; } closest() { return this.matches ? button : null; } }
  const document = {body:{}, fullscreenElement:{},
    querySelector:selector=>selector.includes('title') ? {textContent:'交付线'} : button,
    addEventListener:(type, callback)=>{listeners[type]=callback;},
    exitFullscreen:async()=>{order.push('exit');},
  };
  vm.runInNewContext(navigation.worldMapTaskBridge, {document, Element, addEventListener(){},
    MutationObserver:class {constructor(callback){observer=callback;} observe(){}},
    parent:{postMessage:message=>{order.push('navigate');sent.push(message);}},
  });
  assert.equal(button.textContent, '查看相关任务 →');
  observer();
  let prevented = false;
  const event = {target:new Element(false), preventDefault(){prevented=true;}, stopImmediatePropagation(){}};
  listeners.click(event);
  assert.equal(prevented, false);
  event.target = new Element(true);
  listeners.click(event);
  await Promise.resolve();
  assert.deepEqual(order, ['exit','navigate']);
  assert.equal(sent[0].department, '交付线');
  assert.equal(sent[0].type, 'journey-world-map-tasks');
  assert.equal(prevented, true);
});

test('map parent rejects messages from other windows, unknown departments and non-village maps', () => {
  const source = {postMessage(){}}, received = [];
  let onMessage;
  const component = load('project29/WorldMap.tsx', {
    './worldMap.css':{}, './world-map-navigation':navigation,
    react:{useRef:value=>({current:value === null ? {contentWindow:source} : value}),useState:value=>[value,()=>{}],useEffect:callback=>callback()},
  }, {window:{setTimeout:()=>1,clearTimeout(){},addEventListener:(_, callback)=>{onMessage=callback;}}});
  component.WorldMap({onViewTasks:value=>received.push(value)});
  const data = {type:'journey-world-map-tasks',department:'财务法务合规部'};
  onMessage({source:{},data});
  onMessage({source,data:{...data,department:'其他'}});
  assert.deepEqual(received, []);
  onMessage({source,data});
  assert.deepEqual(received, ['finance-compliance']);
  component.WorldMap({});
  onMessage({source,data});
  assert.equal(received.length, 1);
});

test('new module reads current viewport scale immediately; resize still updates it', () => {
  let value, frame;
  const window = {innerWidth:1440,innerHeight:900,addEventListener:(type, callback)=>{if(type==='resize')window.resize=callback;},removeEventListener(){}};
  const scale = load('project29/useCanvasScale.ts', {
    react:{useSyncExternalStore:(subscribe,snapshot,serverSnapshot)=>{
      assert.equal(serverSnapshot(),1);
      value=snapshot();
      subscribe(()=>{value=snapshot();});
      return value;
    }},
  }, {window,document:{addEventListener(){},removeEventListener(){}},cancelAnimationFrame(){},requestAnimationFrame:callback=>{frame=callback;return 1;}});
  for (let moduleIndex = 0; moduleIndex < 4; moduleIndex++) {
    scale.useCanvasScale();
    assert.equal(value, .75);
    assert.equal(frame, undefined);
  }
  window.innerWidth=960;window.resize();frame();
  assert.equal(value, .5);
});

const flush = () => new Promise(resolve=>setImmediate(resolve));
function loaderHarness(file) {
  let now=0, serial=0;
  const timers = new Map(), images=[];
  let finishFont;
  const mod = load('project29/'+file, {
    './useCanvasScale':{}, './preloadAssets.json':['one.webp','two.webp'], './App':{default:()=>null},
  }, {window:{setTimeout:(callback,delay)=>{timers.set(++serial,{callback,at:now+delay});return serial;},clearTimeout:id=>timers.delete(id)},
    document:{fonts:{load:()=>new Promise(resolve=>{finishFont=()=>resolve([{}]);})}},
    Image:class {constructor(){images.push(this);} decode(){return Promise.resolve();}},
  }, '\nexport const probe={prepare,state:()=>({completed,total,failure,stage})};');
  return {...mod.probe,images,finishFont:()=>finishFont(),advance:time=>{
    now=time;
    for(const [id,timer] of timers)if(timer.at<=now){timers.delete(id);timer.callback();}
  }};
}
for (const file of ['EntryLoader.tsx','AppLoader.tsx']) {
  test(file+': stays loading past 45 seconds and only reaches 100% after all images and font', async () => {
    const loader=loaderHarness(file), pending=loader.prepare();
    await flush();loader.advance(45001);await flush();
    assert.equal(loader.state().failure,false);
    loader.images.forEach(image=>image.onload());await flush();
    assert.ok(loader.state().completed<loader.state().total);
    loader.advance(59999);loader.finishFont();await pending;
    assert.equal(loader.state().failure,false);
    assert.equal(loader.state().completed,loader.state().total);
  });
  test(file+': incomplete resource fails at 60 seconds and remains below 100%', async () => {
    const loader=loaderHarness(file), pending=loader.prepare();
    await flush();loader.advance(60000);await pending;
    assert.equal(loader.state().failure,true);
    assert.ok(loader.state().completed<loader.state().total);
  });
}
