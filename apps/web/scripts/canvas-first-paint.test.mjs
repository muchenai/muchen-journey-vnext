import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const nativeRequire = createRequire(import.meta.url);
const root = fileURLToPath(new URL('../src/', import.meta.url));
const nonce = 'first-paint-request-nonce';
const cache = new Map();
const loadedStyles = new Set();
function load(relativePath) {
  const filename = path.isAbsolute(relativePath) ? relativePath : path.join(root, relativePath);
  if (filename.endsWith('.css')) { loadedStyles.add(filename); return {}; }
  if (filename.endsWith('.json')) return JSON.parse(readFileSync(filename, 'utf8'));
  if (cache.has(filename)) return cache.get(filename).exports;
  const compiledModule = { exports: {} };
  cache.set(filename, compiledModule);
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2022, esModuleInterop: true,
  }, fileName: filename }).outputText;
  const require = name => {
    if (name === 'next/server') return { connection: async () => {} };
    if (name === 'next/headers') return { headers: async () => new Headers({ 'x-nonce': nonce }) };
    if (name === 'next/navigation') return { useRouter: () => ({ refresh() {} }) };
    if (name.endsWith('/actions')) return new Proxy({}, { get: () => () => { throw new Error('Unexpected server action during first paint'); } });
    if (!name.startsWith('.') && !name.startsWith('@/')) return nativeRequire(name);
    const base = name.startsWith('@/') ? path.join(root, name.slice(2)) : path.resolve(path.dirname(filename), name);
    const target = [base, base + '.ts', base + '.tsx'].find(existsSync);
    assert.ok(target, `Missing import ${name}`);
    return load(target);
  };
  vm.runInThisContext('(function(require,module,exports){' + source + '\n})', { filename })(require, compiledModule, compiledModule.exports);
  return compiledModule.exports;
}

function bootstrapViewport(width, height, options = {}) {
  const styles = new Map();
  const frames = new Map();
  const observers = new Set();
  const mutations = [];
  const storage = options.storage ?? new Map();
  let sequence = 0;
  const windowEvents = {}, documentEvents = {};
  const requestAnimationFrame = callback => { frames.set(++sequence, callback); return sequence; };
  const cancelAnimationFrame = id => frames.delete(id);
  const sessionStorage = {
    getItem(key) { return storage.get(key) ?? null; },
    setItem(key, value) { storage.set(key, String(value)); },
    removeItem(key) { storage.delete(key); },
  };
  const window = { innerWidth: width, innerHeight: height,
    outerWidth: options.outerWidth ?? width,
    outerHeight: options.outerHeight ?? height + 100,
    devicePixelRatio: options.pixelRatio ?? 1.25,
    sessionStorage,
    requestAnimationFrame, cancelAnimationFrame,
    addEventListener(type, callback) { windowEvents[type] = callback; } };
  const document = { body: null, documentElement: {
    style: {
      getPropertyValue(name) { return styles.get(name) ?? ''; },
      setProperty(name, value) {
        if (styles.get(name) === String(value)) return;
        styles.set(name, String(value));
        mutations.push({ type: 'attributes', attributeName: 'style', target: document.documentElement });
      },
    },
    removeAttribute(name) {
      assert.equal(name, 'style');
      styles.clear();
      mutations.push({ type: 'attributes', attributeName: 'style', target: document.documentElement });
    },
    setAttribute() { throw new Error('CSP-blocked style attributes must not be used'); },
  }, addEventListener(type, callback) { documentEvents[type] = callback; } };
  class MutationObserver {
    constructor(callback) { this.callback = callback; }
    observe(target, observation) {
      this.target = target;
      this.observation = observation;
      observers.add(this);
    }
    disconnect() { observers.delete(this); }
  }
  const flushMutations = () => {
    for (let round = 0; mutations.length; round += 1) {
      assert.ok(round < 20, 'repairing the scale must not produce an observer write loop');
      const records = mutations.splice(0);
      for (const observer of observers) {
        const matching = records.filter(record => record.target === observer.target && observer.observation.attributes &&
          (!observer.observation.attributeFilter || observer.observation.attributeFilter.includes(record.attributeName)));
        if (matching.length) observer.callback(matching, observer);
      }
    }
  };
  window.MutationObserver = MutationObserver;
  const { canvasScaleBootstrap } = load('app/project29/canvas-scale.ts');
  vm.runInNewContext(canvasScaleBootstrap, { window, document, MutationObserver, sessionStorage, requestAnimationFrame, cancelAnimationFrame });
  flushMutations();
  return { window, document, styles, frames, storage, flushMutations,
    value: () => Number(styles.get('--journey-canvas-scale')),
    dispatch(type) {
      const callback = windowEvents[type] ?? documentEvents[type];
      assert.equal(typeof callback, 'function', `${type} must update viewport scaling`);
      callback();
      flushMutations();
      const pending = [...frames.values()]; frames.clear(); pending.forEach(callback => callback());
      flushMutations();
    },
  };
}

test('a cold document has its final canvas scale before body parsing or React hydration', () => {
  for (const [width, height, expected] of [[1440, 900, 0.75], [1536, 864, 0.8], [1920, 1080, 1], [2560, 1080, 1], [360, 800, 0.1875]]) {
    const viewport = bootstrapViewport(width, height);
    assert.equal(viewport.document.body, null, 'the bootstrap must not need learner DOM to exist');
    assert.equal(viewport.value(), expected, 'the first write must fit the current viewport rather than default to 1');
  }
});

test('the same prepaint scale responds to viewport resize and fullscreen changes', () => {
  const viewport = bootstrapViewport(1440, 900);
  assert.equal(viewport.value(), 0.75);
  viewport.window.innerWidth = 960;
  viewport.dispatch('resize');
  assert.equal(viewport.value(), 0.5);
  viewport.window.innerWidth = 1920;
  viewport.window.innerHeight = 540;
  viewport.dispatch('fullscreenchange');
  assert.equal(viewport.value(), 0.5);
  viewport.window.innerHeight = 1080;
  viewport.dispatch('fullscreenchange');
  assert.equal(viewport.value(), 1);
});

test('login navigation cannot leave the canvas at full size when React removes the root style', () => {
  const viewport = bootstrapViewport(1440, 900);
  assert.equal(viewport.value(), 0.75);
  // Login redirects reconcile the root HTML element before the new page paints.
  viewport.document.documentElement.removeAttribute('style');
  viewport.flushMutations();
  assert.equal(viewport.value(), 0.75, 'restore the fitted scale in the mutation checkpoint before paint');
  assert.equal(viewport.frames.size, 0, 'repair must not wait for a later animation frame');

  // Returning from a task or mounting another module must remain equally stable.
  viewport.document.documentElement.style.setProperty('--journey-canvas-scale', '1');
  viewport.flushMutations();
  assert.equal(viewport.value(), 0.75);
});

test('browser zoom changes the whole canvas instead of being cancelled by automatic fit', () => {
  const viewport = bootstrapViewport(1440, 900);
  const initialScale = viewport.value();
  const initialPixelRatio = viewport.window.devicePixelRatio;
  viewport.window.devicePixelRatio = initialPixelRatio * 1.1;
  viewport.window.innerWidth = 1440 / 1.1;
  viewport.window.innerHeight = 900 / 1.1;
  viewport.dispatch('resize');
  assert.ok(Math.abs(viewport.value() - initialScale) < 0.000001,
    '110% browser zoom must retain the original CSS canvas scale');
  assert.ok(Math.abs((viewport.value() * viewport.window.devicePixelRatio) /
    (initialScale * initialPixelRatio) - 1.1) < 0.000001,
  'the actual canvas must grow by the user-selected 10%');

  viewport.window.devicePixelRatio = initialPixelRatio * 0.8;
  viewport.window.innerWidth = 1440 / 0.8;
  viewport.window.innerHeight = 900 / 0.8;
  viewport.dispatch('resize');
  assert.ok(Math.abs(viewport.value() - initialScale) < 0.000001,
    'zooming out must shrink the complete canvas, without compensating CSS enlargement');

  viewport.window.outerWidth = 960;
  viewport.window.innerWidth = 960 / 0.8;
  viewport.dispatch('resize');
  assert.ok(Math.abs(viewport.value() - 0.5) < 0.000001,
    'a genuine browser-window resize must still adapt the canvas');
});

test('the selected browser zoom survives a fresh document in the same tab', () => {
  const before = bootstrapViewport(1440, 900);
  before.window.devicePixelRatio *= 1.1;
  before.window.innerWidth /= 1.1;
  before.window.innerHeight /= 1.1;
  before.dispatch('resize');
  const after = bootstrapViewport(before.window.innerWidth, before.window.innerHeight, {
    pixelRatio: before.window.devicePixelRatio,
    outerWidth: before.window.outerWidth,
    outerHeight: before.window.outerHeight,
    storage: before.storage,
  });
  assert.ok(Math.abs(after.value() - 0.75) < 0.000001,
    'a login redirect or page refresh must preserve the user-selected browser zoom');
});

test('server layout emits the nonce-authorized synchronous scale script before any page content', async () => {
  const { default: RootLayout } = load('app/layout.tsx');
  const { canvasScaleBootstrap } = load('app/project29/canvas-scale.ts');
  const tree = await RootLayout({ children: React.createElement('main', { id: 'learner-first-paint' }) });
  const html = renderToStaticMarkup(tree);
  const script = html.match(/<script\b[^>]*>[\s\S]*?<\/script>/)?.[0];
  assert.ok(script);
  assert.ok(script.includes(`nonce="${nonce}"`), 'the script must use the request nonce accepted by CSP');
  assert.ok(script.includes(canvasScaleBootstrap));
  assert.doesNotMatch(script, /\s(?:async|defer)(?:=|\s|>)/, 'scaling cannot wait until after first paint');
  assert.ok(html.indexOf(script) < html.indexOf('<body'), 'bootstrap must execute before learner body markup');
  assert.ok(loadedStyles.has(path.join(root, 'app/project29/canvasScale.css')),
    'first-paint scaling needs an external stylesheet, including loader-only documents');
  assert.equal(tree.props.suppressHydrationWarning, true, 'the root owns the intentional bootstrap style mutation');
});

test('all learner canvases use the shared external zoom rule instead of hydration-owned inline zoom', () => {
  const { default: App, Login } = load('app/project29/App.tsx');
  const { JourneyProvider } = load('app/project29/journey-context.tsx');
  const { ProjectResourceLoader } = load('app/project29/EntryLoader.tsx');
  const { AppLoader } = load('app/project29/AppLoader.tsx');
  const canvasMarkup = [];
  for (const initialScreen of ['welcome', 'tasks', 'detail', 'view', 'dashboard', 'village', 'academy', 'guild']) {
    const html = renderToStaticMarkup(React.createElement(App, { initialScreen, learnerName: '真实学员' }));
    canvasMarkup.push(html);
    const stage = ['dashboard', 'village', 'academy', 'guild'].includes(initialScreen) ? 'module-hub' : 'design-stage';
    const element = [...html.matchAll(/<[^>]*\bclass="([^"]*)"[^>]*>/g)].find(match => match[1].split(' ').includes(stage));
    assert.ok(element, `missing ${initialScreen} canvas`);
    assert.ok(element[1].split(' ').includes('journey-scaled-canvas'), `${initialScreen} must use prepaint scaling`);
  }
  const context = { learnerName: '真实学员', experience: null, initialScreen: 'login', joinPhase: 'invite', joinError: '' };
  canvasMarkup.push(renderToStaticMarkup(React.createElement(JourneyProvider, { value: context }, React.createElement(Login))));
  canvasMarkup.push(renderToStaticMarkup(React.createElement(ProjectResourceLoader, { onReady() {} })));
  canvasMarkup.push(renderToStaticMarkup(React.createElement(AppLoader)));
  for (const html of canvasMarkup) {
    assert.match(html, /class="[^"]*journey-scaled-canvas/);
    assert.doesNotMatch(html, /style="[^"]*\bzoom\s*:/, 'no initial zoom=1 may override the external first-paint value');
  }
  const css = readFileSync(path.join(root, 'app/project29/canvasScale.css'), 'utf8');
  assert.match(css, /\.journey-scaled-canvas\s*\{[^}]*zoom\s*:\s*var\(--journey-canvas-scale\s*,\s*1\)/);
});
