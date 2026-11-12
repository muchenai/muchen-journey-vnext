import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const nativeRequire = createRequire(import.meta.url);
const filename = new URL('../src/app/project29/ModuleShell.tsx', import.meta.url);
const compiled = ts.transpileModule(readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const props = { module: 'dashboard', menu: 'hall', identity: '探索者', query: '任务', onQuery() {}, onHome() {}, onProfile() {} };

function loadHeader(react, globals = {}) {
  const loadedModule = { exports: {} };
  const dependencies = {
    react,
    './DashboardTaskGrid': { dashboardStatusLabels: {} },
    './SharedModuleNavigation': { SharedModuleNavigation: () => null },
    './ReviewNotificationBell': { ReviewNotificationBell: () => null },
    './sharedAsset': { sharedAsset: value => value },
  };
  vm.runInNewContext(compiled, {
    ...globals, module: loadedModule, exports: loadedModule.exports,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name),
  });
  return loadedModule.exports.ModuleHeader;
}

function findElement(node, type) {
  if (!node || typeof node !== 'object') return undefined;
  if (Array.isArray(node)) return node.map(child => findElement(child, type)).find(Boolean);
  return node.type === type ? node : findElement(node.props?.children, type);
}

function createHeader(platform = 'Win32') {
  const listeners = new Set();
  const document = {
    activeElement: null, dialogs: [], hidden: false,
    addEventListener(type, listener) { assert.equal(type, 'keydown'); listeners.add(listener); },
    removeEventListener(type, listener) { assert.equal(type, 'keydown'); listeners.delete(listener); },
    querySelectorAll() { return this.dialogs; },
  };
  class Element {
    constructor(tagName = 'BODY', attributes = {}) {
      Object.assign(this, { tagName, visible: true, blockedAncestor: false, isContentEditable: false, focusCount: 0, selectCount: 0 }, attributes);
    }
    closest(selector) {
      if (selector.includes('[hidden]')) return this.blockedAncestor ? this : null;
      return ['INPUT', 'TEXTAREA', 'SELECT'].includes(this.tagName) || this.role === 'textbox' ? this : null;
    }
    getClientRects() { return this.visible ? [{}] : []; }
    focus() { document.activeElement = this; this.focusCount++; }
    select() { this.selectCount++; }
  }
  const body = new Element();
  const input = new Element('INPUT');
  document.activeElement = body;
  const slots = [];
  let cursor = 0;
  let effects = [];
  const react = {
    ...React,
    useRef(value) { return slots[cursor++] ??= { current: value }; },
    useSyncExternalStore(_subscribe, snapshot) { return snapshot(); },
    useEffect(effect, dependencies) {
      const position = cursor++;
      const previous = slots[position];
      if (!previous || dependencies.some((value, index) => !Object.is(value, previous.dependencies[index]))) {
        effects.push(() => {
          previous?.cleanup?.();
          slots[position] = { dependencies, cleanup: effect() };
        });
      }
    },
  };
  const Header = loadHeader(react, {
    document, navigator: { platform }, HTMLElement: Element,
    window: { getComputedStyle: element => ({ visibility: element.visibility || 'visible' }) },
  });
  return {
    document, input, body, Element, listeners,
    render(active = true) {
      cursor = 0;
      effects = [];
      const tree = Header({ ...props, active });
      findElement(tree, 'input').props.ref.current = input;
      effects.forEach(effect => effect());
      return tree;
    },
    press(overrides = {}) {
      const event = {
        key: 'k', ctrlKey: true, metaKey: false, altKey: false, shiftKey: false,
        defaultPrevented: false, isComposing: false, repeat: false, keyCode: 75,
        target: document.activeElement,
        preventDefault() { this.defaultPrevented = true; },
        ...overrides,
      };
      for (const listener of listeners) listener(event);
      return event;
    },
    unmount() { slots.forEach(slot => slot.cleanup?.()); },
  };
}

test('Windows and Linux show Ctrl + K and focus/select the module search', () => {
  for (const platform of ['Win32', 'Linux x86_64']) {
    const flow = createHeader(platform);
    const tree = flow.render();
    assert.equal(findElement(tree, 'kbd').props.children, 'Ctrl + K');
    assert.equal(findElement(tree, 'input').props['aria-keyshortcuts'], 'Control+K');
    assert.equal(flow.press({ ctrlKey: false, metaKey: true }).defaultPrevented, false);
    assert.equal(flow.input.focusCount, 0);
    assert.equal(flow.press().defaultPrevented, true);
    assert.equal(flow.document.activeElement, flow.input);
    assert.equal(flow.input.selectCount, 1);
    flow.press({ key: 'K' });
    assert.equal(flow.input.selectCount, 2, 'the same shortcut selects an existing search query');
  }
});

test('Mac shows and uses Command + K, while server rendering never reads navigator', () => {
  const flow = createHeader('MacIntel');
  const tree = flow.render();
  assert.equal(findElement(tree, 'kbd').props.children, '⌘ K');
  assert.equal(findElement(tree, 'input').props['aria-keyshortcuts'], 'Meta+K');
  assert.equal(flow.press().defaultPrevented, false);
  assert.equal(flow.press({ ctrlKey: false, metaKey: true }).defaultPrevented, true);
  assert.equal(flow.input.focusCount, 1);
  const Header = loadHeader(React);
  const html = renderToStaticMarkup(React.createElement(Header, props));
  assert.match(html, /Ctrl \+ K/);
  assert.match(html, /aria-keyshortcuts="Control\+K"/);
});

test('hidden retained modules and disabled search cannot take focus, and inactive modules remove the listener', () => {
  const flow = createHeader();
  flow.render();
  for (const setting of [{ blockedAncestor: true }, { visible: false }, { disabled: true }, { visibility: 'hidden' }, { visibility: 'collapse' }]) {
    Object.assign(flow.input, { blockedAncestor: false, visible: true, disabled: false, visibility: 'visible' }, setting);
    assert.equal(flow.press().defaultPrevented, false);
  }
  assert.equal(flow.input.focusCount, 0);
  flow.render(false);
  assert.equal(flow.listeners.size, 0);
  Object.assign(flow.input, { blockedAncestor: false, visible: true, disabled: false, visibility: 'visible' });
  assert.equal(flow.press().defaultPrevented, false);
  flow.render(true);
  flow.render(true);
  assert.equal(flow.listeners.size, 1);
  flow.document.hidden = true;
  assert.equal(flow.press().defaultPrevented, false);
  flow.document.hidden = false;
  assert.equal(flow.press().defaultPrevented, true);
  flow.unmount();
  assert.equal(flow.listeners.size, 0);
});

test('composition, handled events, repeated keys and extra modifiers leave normal keyboard behavior intact', () => {
  const flow = createHeader();
  flow.render();
  for (const override of [
    { isComposing: true }, { keyCode: 229 }, { repeat: true }, { altKey: true },
    { shiftKey: true }, { ctrlKey: false }, { metaKey: true }, { key: 'j' },
  ]) assert.equal(flow.press(override).defaultPrevented, false);
  flow.press({ defaultPrevented: true });
  assert.equal(flow.input.focusCount, 0);
});

test('other inputs and rich text editing keep their focus and keyboard shortcut', () => {
  const flow = createHeader();
  flow.render();
  for (const editor of [new flow.Element('INPUT'), new flow.Element('TEXTAREA'), new flow.Element('SELECT'), new flow.Element('DIV', { isContentEditable: true }), new flow.Element('DIV', { role: 'textbox' })]) {
    flow.document.activeElement = editor;
    assert.equal(flow.press().defaultPrevented, false);
    assert.equal(flow.press({ target: flow.body }).defaultPrevented, false);
    flow.document.activeElement = flow.body;
    assert.equal(flow.press({ target: editor }).defaultPrevented, false);
  }
  assert.equal(flow.input.focusCount, 0);
});

test('visible dialogs block the page shortcut, and closed or hidden dialogs allow it again', () => {
  const flow = createHeader();
  flow.render();
  flow.document.dialogs = [new flow.Element('DIALOG')];
  assert.equal(flow.press().defaultPrevented, false);
  assert.equal(flow.input.focusCount, 0);
  flow.document.dialogs[0].visible = false;
  assert.equal(flow.press().defaultPrevented, true);
  flow.document.dialogs = [];
  assert.equal(flow.press().defaultPrevented, true);
});
