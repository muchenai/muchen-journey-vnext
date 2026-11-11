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
  vm.runInNewContext(code, {module: compiledModule, exports:compiledModule.exports, URL, Response, ...globals,
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

test('map task button captures its department and departs before fullscreen exit or navigation', async () => {
  const listeners = {}, sent = [], order = [];
  let observer;
  const attributes = new Set();
  const button = {textContent:'返回地图', toggleAttribute(name, enabled) { if(enabled) attributes.add(name); else attributes.delete(name); }};
  const title = {textContent:'交付线'};
  const parent = {postMessage:message=>{order.push('navigate');sent.push(message);}};
  class Element { constructor(matches) { this.matches = matches; } closest() { return this.matches ? button : null; } }
  class Event { constructor(type) {this.type=type;} }
  const document = {body:{}, fullscreenElement:{},
    querySelector:selector=>selector.includes('title') ? title : button,
    addEventListener:(type, callback)=>{listeners[type]=callback;},
    dispatchEvent(event) {
      assert.equal(event.type, 'journey-world-map-depart');
      order.push('depart');
      title.textContent = '';
    },
    exitFullscreen:async()=>{order.push('exit');},
  };
  vm.runInNewContext(navigation.worldMapTaskBridge, {document, Element, Event, addEventListener(type, callback){listeners[type]=callback;},
    MutationObserver:class {constructor(callback){observer=callback;} observe(){}},
    parent,
  });
  assert.equal(button.textContent, '探索相关任务 →');
  observer();
  let prevented = false;
  const event = {target:new Element(false), preventDefault(){prevented=true;}, stopImmediatePropagation(){}};
  listeners.click(event);
  assert.equal(prevented, false);
  assert.deepEqual(order, [], 'closing a detail does not start task departure');
  event.target = new Element(true);
  listeners.click(event);
  assert.deepEqual(order, ['depart','exit'], 'departure starts synchronously before the fullscreen promise settles');
  await Promise.resolve();
  assert.deepEqual(order, ['depart','exit','navigate']);
  assert.equal(sent[0].department, '交付线');
  assert.equal(sent[0].type, 'journey-world-map-tasks');
  assert.equal(prevented, true);
  listeners.message({source:parent,data:{type:'journey-world-map-context',village:false}});
  assert.equal(button.textContent, '返回地图');
  assert.equal(attributes.has('data-village-task-link'), false);
  prevented = false;
  listeners.click(event);
  assert.equal(prevented, false);
  listeners.message({source:parent,data:{type:'journey-world-map-context',village:true}});
  assert.equal(button.textContent, '探索相关任务 →');
  assert.equal(attributes.has('data-village-task-link'), true);
  document.fullscreenElement = null;
  title.textContent = '财务法务合规部';
  order.length = 0;
  listeners.click(event);
  assert.deepEqual(order, ['depart','navigate']);
  assert.equal(sent[1].department, '财务法务合规部', 'resetting the title must not change the captured destination');
});

function mapParentHarness() {
  const slots = [], sent = [], received = [];
  const source = {postMessage:message => sent.push(message)};
  const listeners = new Map();
  let cursor = 0, effects = [], mapChildren = [];
  const sameDependencies = (previous, next) => previous && next &&
    previous.length === next.length && next.every((value, index) => Object.is(value, previous[index]));
  const component = load('project29/WorldMap.tsx', {
    './worldMap.css':{}, './world-map-navigation':navigation,
    react:{
      useState(initial) {
        const index = cursor++;
        if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
        return [slots[index], value => {slots[index] = typeof value === 'function' ? value(slots[index]) : value;}];
      },
      useRef(initial) {
        const index = cursor++;
        return slots[index] ??= {current:initial};
      },
      useMemo(factory, dependencies) {
        const index = cursor++, previous = slots[index];
        if (!previous || !sameDependencies(previous.dependencies, dependencies)) {
          slots[index] = {dependencies, value:factory()};
        }
        return slots[index].value;
      },
      useEffect(callback, dependencies) {
        const index = cursor++, previous = slots[index];
        if (!previous || !sameDependencies(previous.dependencies, dependencies)) {
          effects.push(() => {previous?.cleanup?.(); slots[index] = {dependencies, cleanup:callback()};});
        }
      },
    },
  }, {window:{setTimeout:()=>1,clearTimeout(){},addEventListener:(type, callback)=>listeners.set(type, callback),removeEventListener:type=>listeners.delete(type)}});
  const onViewTasks = value => received.push(value);
  const commit = () => {
    const pending = effects;
    effects = [];
    for (const effect of pending) effect();
  };
  const render = (props = {}, runEffects = true) => {
    cursor = 0; effects = [];
    const tree = component.WorldMap({contextKey:'village', active:true, onViewTasks, ...props});
    mapChildren = tree.props.children[0].props.children;
    const iframe = mapChildren[0];
    iframe.props.ref.current = {contentWindow:source};
    if (runEffects) commit();
    return iframe;
  };
  const message = (data, from = source) => listeners.get('message')({source:from, data});
  const resets = () => sent.filter(item => item.type === 'journey-world-map-reset');
  return {render, commit, message, resets, sent, source, received,
    ready:() => message({type:'journey-world-map-ready'}),
    acknowledge:(requestId, from = source) => message({type:'journey-world-map-reset-complete', requestId}, from),
    presented:(requestId, from = source) => message({type:'journey-world-map-presented', requestId}, from),
    presentations:() => sent.filter(item => item.type === 'journey-world-map-present'),
    cover:() => mapChildren.find(child => child?.props?.className === 'world-map-presentation-cover') ?? null,
    context:() => sent.filter(item => item.type === 'journey-world-map-context').at(-1),
  };
}

test('map parent accepts tasks only after preparation and painting of its current view', () => {
  const flow = mapParentHarness();
  const task = {type:'journey-world-map-tasks', department:'财务法务合规部'};
  assert.equal(flow.render().props['data-presented'], false);
  flow.message(task);
  flow.message({type:'journey-world-map-ready'}, {});
  flow.render();
  assert.equal(flow.resets().length, 0, 'another window cannot mark the map ready');
  assert.deepEqual(flow.received, []);
  flow.ready();
  assert.equal(flow.render().props['data-presented'], false, 'decoded resources alone must not reveal the map');
  const request = flow.resets().at(-1);
  assert.ok(Number.isSafeInteger(request.requestId));
  assert.equal(flow.context().active, false);
  flow.presented(request.requestId);
  assert.equal(flow.render().props['data-prepared'], false, 'paint acknowledgement cannot skip DOM preparation');
  assert.equal(flow.presentations().length, 0);
  flow.acknowledge(request.requestId, {});
  flow.acknowledge(request.requestId + 1);
  flow.acknowledge(undefined);
  assert.equal(flow.render().props['data-presented'], false);
  flow.message(task);
  assert.deepEqual(flow.received, [], 'navigation stays closed until the matching reset has completed');
  flow.acknowledge(request.requestId);
  const prepared = flow.render({}, false);
  assert.equal(prepared.props['data-prepared'], true);
  assert.equal(prepared.props['data-presented'], false, 'a prepared iframe stays under its opaque cover');
  assert.ok(flow.cover(), 'the paintable iframe must remain covered until its paint acknowledgement');
  flow.presented(request.requestId);
  flow.commit();
  assert.equal(flow.render().props['data-presented'], false,
    'a paint ACK received before the presentation request cannot reveal the frame');
  assert.equal(flow.presentations().at(-1).requestId, request.requestId);
  assert.equal(flow.context().active, false);
  flow.message(task);
  assert.deepEqual(flow.received, [], 'DOM readiness must not enable task navigation or animations');
  flow.render();
  assert.equal(flow.presentations().length, 1, 'a render alone cannot request another painting pass');
  flow.presented(request.requestId, {});
  flow.presented(request.requestId + 1);
  flow.presented(undefined);
  assert.equal(flow.render().props['data-presented'], false);
  flow.presented(request.requestId);
  assert.equal(flow.render().props['data-presented'], true);
  assert.equal(flow.cover(), null);
  assert.equal(flow.context().active, true);
  flow.message(task, {});
  flow.message({...task, department:'其他'});
  assert.deepEqual(flow.received, []);
  flow.message(task);
  assert.deepEqual(flow.received, ['finance-compliance']);
  flow.message(task);
  assert.equal(flow.received.length, 1, 'departure closes task navigation synchronously before another render');
  flow.acknowledge(request.requestId);
  flow.presented(request.requestId);
  const departing = flow.render();
  assert.equal(departing.props['data-prepared'], false);
  assert.equal(departing.props['data-presented'], false, 'old acknowledgements cannot reveal a departed view');
  assert.ok(flow.cover());
  flow.render({onViewTasks:undefined});
  flow.message(task);
  assert.equal(flow.received.length, 1, 'maps without a task callback retain their original interactions');
  flow.render({active:false});
  flow.message(task);
  assert.equal(flow.received.length, 1, 'a hidden map cannot navigate even with a valid department');
  assert.equal(flow.context().active, false);
});

test('shared map hides each new view before effects, ignores stale acknowledgements and never reloads for navigation', () => {
  const flow = mapParentHarness();
  const initial = flow.render({contextKey:'academy'});
  assert.equal(initial.props['data-presented'], false);
  flow.render({contextKey:'village', active:false});
  flow.render({contextKey:'guild'});
  assert.equal(flow.resets().length, 0, 'reset requests wait for the iframe document to be ready');
  flow.ready();
  flow.render({contextKey:'guild'});
  assert.equal(flow.resets().length, 1);
  const firstGuild = flow.resets().at(-1);
  flow.acknowledge(firstGuild.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
  flow.presented(firstGuild.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], true);
  flow.render({contextKey:'guild'});
  assert.equal(flow.resets().length, 1, 'ordinary rerenders keep the same view token');

  const academy = flow.render({contextKey:'academy'}, false);
  assert.equal(academy.props['data-presented'], false, 'a context change hides the iframe in its first render');
  assert.equal(academy.props['data-prepared'], false);
  flow.commit();
  const academyReset = flow.resets().at(-1);
  const guild = flow.render({contextKey:'guild'}, false);
  assert.equal(guild.props['data-presented'], false, 'A → B → A must not reuse A\'s old presented view');
  flow.commit();
  const latestGuild = flow.resets().at(-1);
  assert.equal(flow.resets().length, 3);
  assert.ok(firstGuild.requestId < academyReset.requestId && academyReset.requestId < latestGuild.requestId);
  flow.presented(latestGuild.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false, 'an early paint ACK is not accepted');
  for (const stale of [firstGuild, academyReset]) {
    flow.acknowledge(stale.requestId);
    flow.presented(stale.requestId);
    assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
    assert.equal(flow.context().active, false);
  }
  flow.acknowledge(latestGuild.requestId);
  const preparedGuild = flow.render({contextKey:'guild'});
  assert.equal(preparedGuild.props['data-prepared'], true);
  assert.equal(preparedGuild.props['data-presented'], false);
  for (const stale of [firstGuild, academyReset]) flow.presented(stale.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
  flow.presented(latestGuild.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], true);

  const hidden = flow.render({contextKey:'guild', active:false}, false);
  assert.equal(hidden.props['data-presented'], false, 'leaving the map creates an unpresented view immediately');
  flow.commit();
  const hiddenReset = flow.resets().at(-1);
  assert.equal(flow.resets().length, 4);
  const presentationsBeforeHiding = flow.presentations().length;
  flow.acknowledge(hiddenReset.requestId);
  const preparedHidden = flow.render({contextKey:'guild', active:false});
  assert.equal(preparedHidden.props['data-prepared'], true);
  assert.equal(preparedHidden.props['data-presented'], false);
  assert.equal(flow.presentations().length, presentationsBeforeHiding, 'hidden views do not wait for animation frames');
  flow.presented(hiddenReset.requestId);
  assert.equal(flow.render({contextKey:'guild', active:false}).props['data-presented'], false);
  assert.equal(flow.context().active, false, 'acknowledging a hidden view must not resume its animations');
  const reentered = flow.render({contextKey:'guild'}, false);
  assert.equal(reentered.props['data-presented'], false, 'same-module reentry also starts at an unpresented overview');
  flow.commit();
  const reentryReset = flow.resets().at(-1);
  assert.equal(flow.resets().length, 5);
  flow.acknowledge(hiddenReset.requestId);
  flow.presented(latestGuild.requestId);
  flow.presented(hiddenReset.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
  flow.acknowledge(reentryReset.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
  flow.presented(latestGuild.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], false);
  flow.presented(reentryReset.requestId);
  assert.equal(flow.render({contextKey:'guild'}).props['data-presented'], true);
  flow.render({contextKey:'guild'});
  assert.equal(flow.resets().length, 5);
  for (const iframe of [academy, guild, preparedGuild, hidden, preparedHidden, reentered]) {
    assert.equal(iframe.props.src, initial.props.src);
    assert.equal(iframe.key, initial.key, 'view changes must preserve the loaded iframe and its resources');
  }
});

function instantResetHarness() {
  const bridge = load('project29/world-map-loading.ts').worldMapInstantResetBridge;
  assert.equal(typeof bridge, 'string');
  const attributes = new Set(), timers = new Map(), frames = new Map(), sent = [], events = [];
  const documentListeners = new Map();
  const blockers = new Set(['.universe.has-selection', '.planet-detail', '.focus-flight']);
  const values = {'--zoom':'1.2', '--pan-x':'20px', '--pan-y':'10px'};
  const state = {buttonAvailable:true, clicks:0, frameRequests:0};
  let listener, observer, serial = 0;
  const root = {
    setAttribute(name) { attributes.add(name); events.push(`set:${name}`); },
    removeAttribute(name) { attributes.delete(name); events.push(`remove:${name}`); },
  };
  const scene = {style:{getPropertyValue:name => values[name]}};
  const universe = {getBoundingClientRect() {events.push('layout');return {};}, querySelectorAll:() => [scene, {}]};
  const parent = {postMessage(message) {sent.push(message);events.push(message.type);}};
  const document = {body:{}, documentElement:root,
    addEventListener(type, callback) {documentListeners.set(type, callback);},
    querySelector(selector) {
    if (selector === '.universe') return universe;
    if (selector === '.cosmos-scene') return scene;
    if (selector === 'button[aria-label="重置视图"]') return state.buttonAvailable ? {click() {state.clicks += 1;}} : null;
    return selector.split(',').some(part => blockers.has(part)) ? {} : null;
  }};
  vm.runInNewContext(bridge, {document, parent,
    MutationObserver:class {constructor(callback) {observer=callback;} observe() {}},
    addEventListener(type, callback) {assert.equal(type, 'message');listener=callback;},
    setTimeout(callback, delay) {timers.set(++serial, {callback, delay});return serial;},
    clearTimeout(id) {timers.delete(id);},
    requestAnimationFrame(callback) {state.frameRequests += 1;frames.set(++serial, callback);return serial;},
    cancelAnimationFrame(id) {frames.delete(id);},
    getComputedStyle() {
      return Object.defineProperties({}, Object.fromEntries(['transform', 'opacity', 'filter', 'scale', 'rotate']
        .map(property => [property, {get() {
          events.push(`style:${attributes.has('data-map-resetting') ? 'suppressed' : 'normal'}:${property}`);
          return 'none';
        }}])));
    },
  });
  return {attributes, timers, frames, sent, events, blockers, values, state, mutate:() => observer(),
    depart:() => documentListeners.get('journey-world-map-depart')({type:'journey-world-map-depart'}),
    reset:(requestId, from = parent) => listener({source:from, data:{type:'journey-world-map-reset', requestId}}),
    present:(requestId, from = parent) => listener({source:from, data:{type:'journey-world-map-present', requestId}}),
    overview() {blockers.clear();Object.assign(values, {'--zoom':'1', '--pan-x':'0px', '--pan-y':'0px'});observer();},
    advance() {for (const [id, timer] of [...timers]) {timers.delete(id);timer.callback();}},
    paint() {for (const [id, callback] of [...frames]) {frames.delete(id);callback();}},
  };
}

test('instant map reset prepares without frames and reveals only after two requested paint frames', () => {
  const flow = instantResetHarness();
  flow.reset(1, {});
  for (const requestId of [undefined, null, '1', 0.5, Infinity, Number.MAX_SAFE_INTEGER + 1]) flow.reset(requestId);
  assert.equal(flow.attributes.size, 0);
  assert.equal(flow.state.clicks, 0);
  flow.reset(1);
  flow.present(1);
  assert.equal(flow.state.frameRequests, 0, 'an unprepared view cannot start its painting phase');
  assert.equal(flow.attributes.has('data-map-resetting'), true);
  assert.equal(flow.state.clicks, 1);
  assert.equal(flow.timers.size, 0, 'selected content must disappear before acknowledgement is scheduled');
  Object.assign(flow.values, {'--zoom':'1', '--pan-x':'0px', '--pan-y':'0px'});
  for (const blocker of ['.universe.has-selection', '.planet-detail', '.focus-flight', '.focus-instruction',
    '.planet-node.is-selected', '.planet-node.is-in-flight']) {
    flow.blockers.clear();flow.blockers.add(blocker);flow.mutate();
    assert.equal(flow.timers.size, 0, `${blocker} must block acknowledgement`);
  }
  flow.blockers.clear();
  for (const [property, value] of [['--zoom', '1.2'], ['--pan-x', '20px'], ['--pan-y', '-10px']]) {
    const original = flow.values[property];
    flow.values[property] = value;flow.mutate();
    assert.equal(flow.timers.size, 0, 'the camera must be back at its overview position');
    flow.values[property] = original;
  }
  flow.overview();
  assert.equal(flow.sent.length, 0, 'DOM commit alone still waits a task for canvas cleanup');
  assert.equal(flow.timers.size, 1);
  assert.equal([...flow.timers.values()][0].delay, 0);
  flow.advance();
  assert.equal(flow.attributes.has('data-map-resetting'), true, 'motion suppression survives DOM readiness');
  assert.equal(flow.sent.length, 1);
  assert.equal(flow.sent[0].type, 'journey-world-map-reset-complete');
  assert.equal(flow.sent[0].requestId, 1);
  assert.equal(flow.state.frameRequests, 0, 'a hidden iframe must reach DOM readiness without any animation frame');
  flow.mutate();flow.advance();
  assert.equal(flow.sent.length, 1, 'later mutations cannot acknowledge the same reset twice');
  flow.present(1, {});
  for (const requestId of [undefined, '1', 0.5, 2]) flow.present(requestId);
  assert.equal(flow.state.frameRequests, 0, 'only the matching parent may start presentation');
  flow.present(1);
  assert.equal(flow.frames.size, 1);
  flow.paint();
  assert.equal(flow.sent.length, 1, 'one frame is insufficient to reveal the overview');
  assert.equal(flow.attributes.has('data-map-resetting'), true);
  assert.equal(flow.frames.size, 1);
  flow.paint();
  assert.equal(flow.frames.size, 0);
  assert.equal(flow.attributes.has('data-map-resetting'), false);
  assert.equal(flow.sent.length, 2);
  assert.equal(flow.sent[1].type, 'journey-world-map-presented');
  assert.equal(flow.sent[1].requestId, 1);
  const release = flow.events.indexOf('remove:data-map-resetting'), ack = flow.events.indexOf('journey-world-map-presented');
  assert.ok(flow.events.slice(0, release).includes('style:suppressed:transform'));
  assert.ok(flow.events.slice(release + 1, ack).includes('style:normal:opacity'),
    'final computed styles are flushed after restoring animations and before acknowledgement');
  flow.mutate();flow.advance();flow.present(1);flow.paint();
  assert.equal(flow.sent.length, 2, 'a completed presentation cannot be acknowledged twice');
});

test('instant map reset waits for mounted controls and ignores a superseded settle callback', () => {
  const flow = instantResetHarness();
  flow.state.buttonAvailable = false;
  flow.reset(7);
  assert.equal(flow.state.clicks, 0);
  assert.equal(flow.sent.length, 0);
  flow.state.buttonAvailable = true;flow.mutate();
  assert.equal(flow.state.clicks, 1);
  flow.overview();
  const stale = [...flow.timers.values()][0].callback;
  flow.reset(8);
  assert.equal(flow.state.clicks, 2);
  stale();
  assert.equal(flow.sent.length, 0, 'an earlier request cannot reveal a later view');
  flow.blockers.add('.focus-flight');flow.advance();
  assert.equal(flow.sent.length, 0, 'the overview is checked again after the settle task');
  assert.equal(flow.attributes.has('data-map-resetting'), true);
  flow.overview();flow.advance();
  assert.equal(flow.sent.length, 1);
  assert.equal(flow.sent[0].requestId, 8);
  assert.equal(flow.state.frameRequests, 0);
});

test('instant map presentation cancels either pending frame on a new reset and rechecks the overview', () => {
  for (const completedFrames of [0, 1]) {
    const flow = instantResetHarness();
    flow.reset(11);flow.overview();flow.advance();flow.present(11);
    if (completedFrames) flow.paint();
    const staleFrame = [...flow.frames.values()][0];
    assert.equal(typeof staleFrame, 'function');
    flow.reset(12);
    assert.equal(flow.frames.size, 0, 'new reset cancels the old frame callback');
    staleFrame();
    assert.equal(flow.sent.filter(message => message.type === 'journey-world-map-presented').length, 0);
    assert.equal(flow.attributes.has('data-map-resetting'), true);
    flow.overview();flow.advance();flow.present(12);flow.paint();flow.paint();
    assert.deepEqual(Array.from(flow.sent.filter(message => message.type === 'journey-world-map-presented'), message => message.requestId), [12]);
  }
  const regressed = instantResetHarness();
  regressed.reset(20);regressed.overview();regressed.advance();regressed.present(20);regressed.paint();
  regressed.blockers.add('.focus-flight');
  regressed.paint();
  assert.equal(regressed.sent.filter(message => message.type === 'journey-world-map-presented').length, 0,
    'a newly visible flight during painting must keep the cover in place');
  assert.equal(regressed.attributes.has('data-map-resetting'), true);
});

test('map departure resets in the background without acknowledgements or frames and stays hidden until the next presentation', () => {
  const flow = instantResetHarness();
  flow.depart();
  assert.equal(flow.attributes.has('data-map-departing'), true, 'the departing focus is hidden in the same event');
  assert.equal(flow.attributes.has('data-map-resetting'), true);
  assert.equal(flow.state.clicks, 1, 'departure invokes the native overview reset immediately');
  assert.equal(flow.sent.length, 0);
  assert.equal(flow.state.frameRequests, 0);
  flow.overview();flow.advance();
  assert.equal(flow.sent.length, 0, 'a background reset has no parent request to acknowledge');
  assert.equal(flow.state.frameRequests, 0, 'restoring a departed map never waits for hidden animation frames');
  assert.equal(flow.attributes.has('data-map-departing'), true);
  flow.present(null);flow.present(40);flow.paint();
  assert.equal(flow.state.frameRequests, 0);
  assert.equal(flow.attributes.has('data-map-departing'), true);

  flow.reset(41);flow.overview();flow.advance();
  assert.equal(flow.sent.length, 1);
  assert.equal(flow.sent[0].type, 'journey-world-map-reset-complete');
  assert.equal(flow.sent[0].requestId, 41);
  assert.equal(flow.attributes.has('data-map-departing'), true, 'DOM readiness alone must not reveal the outgoing map');
  flow.present(40);
  assert.equal(flow.attributes.has('data-map-departing'), true);
  flow.present(41);
  assert.equal(flow.attributes.has('data-map-departing'), false, 'the real parent presentation makes the overview paintable behind its cover');
  assert.equal(flow.attributes.has('data-map-resetting'), true);
  flow.paint();
  assert.equal(flow.sent.length, 1);
  flow.paint();
  assert.equal(flow.sent.length, 2);
  assert.equal(flow.sent[1].type, 'journey-world-map-presented');
  assert.equal(flow.sent[1].requestId, 41);
});

test('map departure cancels a prior presentation so its stale frame cannot acknowledge the new background reset', () => {
  const flow = instantResetHarness();
  flow.reset(50);flow.overview();flow.advance();flow.present(50);flow.paint();
  const oldFrame = [...flow.frames.values()][0];
  flow.depart();
  assert.equal(flow.frames.size, 0);
  assert.equal(flow.attributes.has('data-map-departing'), true);
  oldFrame();
  flow.overview();flow.advance();
  assert.equal(flow.sent.length, 1, 'departure sends neither an old painted ACK nor a new unsolicited DOM ACK');
  assert.equal(flow.attributes.has('data-map-departing'), true);
  flow.reset(51);flow.overview();flow.advance();flow.present(51);flow.paint();flow.paint();
  assert.deepEqual(Array.from(flow.sent.filter(message => message.type === 'journey-world-map-presented'), message => message.requestId), [51]);
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
