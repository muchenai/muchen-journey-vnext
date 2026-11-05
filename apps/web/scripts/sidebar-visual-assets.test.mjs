import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const nativeRequire = createRequire(import.meta.url);
const components = new URL('../src/app/project29/', import.meta.url);
const publicFiles = new URL('../public/', import.meta.url);

function loadComponent(file, dependencies = {}) {
  const source = ts.transpileModule(readFileSync(new URL(file, components), 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(source, {
    module: compiledModule, exports: compiledModule.exports,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name),
  });
  return compiledModule.exports;
}

const aliases = JSON.parse(readFileSync(new URL('assetAliases.json', components), 'utf8'));
const sharedAsset = loadComponent('sharedAsset.ts', { './assetAliases.json': aliases });
const navigation = loadComponent('SharedModuleNavigation.tsx');
const { ModuleIcon } = loadComponent('ModuleShell.tsx', {
  './DashboardTaskGrid': { dashboardStatusLabels: {} },
  './SharedModuleNavigation': navigation,
  './sharedAsset': sharedAsset,
  './ReviewNotificationBell': { ReviewNotificationBell: () => null },
});

test('initial icon markup keeps dimensions and asset masks when CSP rejects style attributes', () => {
  const inputs = [
    { file: '8c48a', size: 24 },
    { file: '8c48a', size: 13 },
    { file: '93f75', size: 24 },
    { file: '643cc', size: 42 },
    { file: '0c76d', size: 24 },
    { file: 'f4e78', size: 24 },
    { file: 'a03b5', pack: 'guild', size: 58 },
  ];
  const html = renderToStaticMarkup(React.createElement(React.Fragment, null,
    ...inputs.map((props, index) => React.createElement(ModuleIcon, { ...props, key: index })),
  ));
  assert.doesNotMatch(html, /\sstyle=/, 'initial dimensions and masks must survive strict CSP');
  const icons = [...html.matchAll(/<svg\b[^>]*>[\s\S]*?<\/svg>/g)].map(match => match[0]);
  assert.equal(icons.length, inputs.length);
  const maskIds = new Set();
  icons.forEach((icon, index) => {
    const props = inputs[index];
    const opening = icon.slice(0, icon.indexOf('>') + 1);
    assert.match(opening, new RegExp(`\\bwidth="${props.size}"`));
    assert.match(opening, new RegExp(`\\bheight="${props.size}"`));
    assert.match(opening, /viewBox="0 0 24 24"/);
    const id = icon.match(/<mask\b[^>]*\bid="([^"]+)"/)?.[1];
    assert.ok(id, 'every icon needs its own SVG mask');
    assert.ok(!maskIds.has(id), 'simultaneously mounted icons must not share mask IDs');
    maskIds.add(id);
    assert.ok(icon.includes(`mask="url(#${id})"`), 'the painted shape must reference its own mask');
    assert.match(icon, /<rect\b[^>]*\bfill="currentColor"/);
    const href = icon.match(/<image\b[^>]*\bhref="([^"]+)"/)?.[1];
    assert.equal(href, sharedAsset.sharedAsset(`/assets/project29/modules/${props.pack ?? 'academy'}/${props.file}.svg`));
    assert.ok(href.startsWith('/assets/'), 'icons must resolve to local assets');
    const asset = new URL(href.slice(1), publicFiles);
    assert.ok(existsSync(asset), `missing icon asset: ${href}`);
    assert.match(readFileSync(asset, 'utf8'), /<svg\b/);
  });
});

test('icon styles retain alpha masks without painting a solid background over the SVG', () => {
  const css = ['moduleHub.css', 'journeyDialog.css']
    .map(file => readFileSync(new URL(file, components), 'utf8')).join('\n');
  assert.match(css, /\.module-icon-mask\s*\{[^}]*mask-type\s*:\s*alpha/);
  const iconRules = [...css.matchAll(/[^{}]*\.module-icon\b[^{}]*\{([^}]*)\}/g)];
  assert.ok(iconRules.length > 0);
  for (const [, rule] of iconRules) {
    assert.doesNotMatch(rule, /background(?:-color)?\s*:\s*currentColor/i,
      'SVG icons must not inherit the old span mask background');
  }
});

test('the shared wordmark is visible from external styles on every module initial render', () => {
  const css = readFileSync(new URL('index.css', components), 'utf8');
  const gradientRule = css.match(/\.dashboard-brand-gradient\s*\{[^}]*\}/)?.[0] ?? '';
  assert.match(gradientRule, /background(?:-image)?\s*:[^}]*linear-gradient/);
  assert.match(gradientRule, /background-clip\s*:\s*text/);
  for (const moduleName of ['dashboard', 'village', 'academy', 'guild']) {
    const html = renderToStaticMarkup(React.createElement(navigation.SharedModuleNavigation, {
      module: moduleName, onNavigate() {}, activeDecoration: null, idleDecoration: null,
    }, null));
    const wordmark = html.match(/<div\b[^>]*data-node-id="4062:469"[^>]*>[\s\S]*?<\/div>/)?.[0];
    assert.ok(wordmark, `missing shared wordmark in ${moduleName}`);
    assert.match(wordmark, /MUCHEN/);
    assert.match(wordmark, /JOURNEY/);
    assert.match(wordmark, /dashboard-brand-gradient/);
    assert.doesNotMatch(wordmark, /\sstyle=/, 'wordmark gradients cannot depend on CSP-blocked attributes');
  }
});
