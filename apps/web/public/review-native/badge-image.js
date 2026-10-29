const MAX_BYTES = 2 * 1024 * 1024;
const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';
const XML_NS = 'http://www.w3.org/XML/1998/namespace';
const XMLNS_NS = 'http://www.w3.org/2000/xmlns/';
const ELEMENTS = new Set('svg g defs path rect circle ellipse line polyline polygon text tspan title desc linearGradient radialGradient stop clipPath mask'.split(' '));
const ATTRIBUTES = new Set(('id x y x1 y1 x2 y2 cx cy r rx ry width height viewBox preserveAspectRatio d points transform ' +
  'fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset ' +
  'opacity color display visibility vector-effect clip-path clip-rule mask font-family font-size font-weight font-style text-anchor dominant-baseline alignment-baseline ' +
  'letter-spacing word-spacing dx dy rotate textLength lengthAdjust gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity fx fy fr clipPathUnits maskUnits maskContentUnits style href').split(' '));
const STYLE_PROPERTIES = new Set(('fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset ' +
  'opacity color display visibility vector-effect clip-path clip-rule mask font-family font-size font-weight font-style text-anchor dominant-baseline alignment-baseline letter-spacing word-spacing stop-color stop-opacity').split(' '));
const ID = /^[A-Za-z_][A-Za-z0-9_.:-]*$/;
const DATA_IMAGE = /^data:image\/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/]+={0,2})$/i;

function fail(message) { throw new Error(message); }

function base64Bytes(value) {
  if (value.length % 4 || value.length > Math.ceil(MAX_BYTES / 3) * 4) fail('徽章图片不能超过 2MB，且必须是有效图片文件。');
  let binary;
  try { binary = atob(value); } catch { fail('徽章图片编码无效，请重新上传。'); }
  if (binary.length > MAX_BYTES) fail('徽章图片不能超过 2MB。');
  if (btoa(binary) !== value) fail('徽章图片编码无效，请重新上传。');
  return Uint8Array.from(binary, char => char.charCodeAt(0));
}

function encodeBase64(bytes) {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 8192) binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
  return btoa(binary);
}

function decodeUTF8(bytes) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { fail('SVG 徽章请使用 UTF-8 编码。'); }
}

function checkDimension(value) {
  const match = String(value).trim().match(/^(\d*\.?\d+)(?:px)?$/);
  return !!match && Number(match[1]) > 0 && Number(match[1]) <= 4096;
}

function sanitizeSVG(source) {
  if (new TextEncoder().encode(source).length > MAX_BYTES) fail('SVG 徽章不能超过 2MB。');
  if (/<!DOCTYPE|<!ENTITY/i.test(source)) fail('SVG 徽章不能包含文档类型或外部实体声明。');
  const document = new DOMParser().parseFromString(source, 'image/svg+xml');
  const root = document.documentElement;
  if (!root || root.localName !== 'svg' || document.getElementsByTagName('parsererror').length) fail('SVG 内容格式不正确，请粘贴完整的 <svg> 代码。');
  for (const node of Array.from(document.childNodes)) {
    if (node.nodeType === 7 || node.nodeType === 10) fail('SVG 徽章不支持外部样式或文档声明。');
  }

  let elements = 0;
  let pathTokens = 0;
  let gradients = 0;
  let stops = 0;
  const ids = new Map();
  const references = [];
  const nodes = [];

  function valueReferences(value, owner, property) {
    if (/[\\]|\/\*|\*\/|expression\s*\(|@|(?:javascript|vbscript|data|https?|file|ftp):/i.test(value)) fail('SVG 徽章只能使用静态图形，不能包含脚本或外部资源。');
    const remainder = value.replace(/url\(\s*(['"]?)#([A-Za-z_][A-Za-z0-9_.:-]*)\1\s*\)/gi, (_match, _quote, id) => {
      if (!['fill', 'stroke', 'clip-path', 'mask'].includes(property)) fail('SVG 徽章包含不支持的资源引用。');
      references.push({ owner, id, property });
      return '';
    });
    if (/url\s*\(/i.test(remainder)) fail('SVG 徽章的图形引用只能指向文件内部的 #id。');
  }

  function visit(node, depth) {
    if (depth > 32 || ++elements > 1500) fail('SVG 徽章图形过于复杂，请简化后再上传。');
    if ((node.namespaceURI && node.namespaceURI !== SVG_NS) || !ELEMENTS.has(node.localName)) fail('SVG 徽章仅支持静态形状、文字、分组、渐变和遮罩。');
    if (node !== root && node.localName === 'svg') fail('SVG 徽章请只保留一个最外层 <svg>。');
    if (/Gradient$/.test(node.localName) && ++gradients > 64) fail('SVG 徽章渐变过多，请简化后再上传。');
    if (node.localName === 'stop' && ++stops > 512) fail('SVG 徽章渐变节点过多，请简化后再上传。');
    nodes.push(node);

    for (const attr of Array.from(node.attributes)) {
      const name = attr.localName;
      const value = attr.value.trim();
      if (attr.namespaceURI === XMLNS_NS || attr.name === 'xmlns') {
        if (!((attr.name === 'xmlns' && value === SVG_NS) || (attr.name === 'xmlns:xlink' && value === XLINK_NS))) fail('SVG 徽章包含不支持的命名空间。');
        continue;
      }
      if (attr.namespaceURI === XML_NS && name === 'space' && /^(default|preserve)$/.test(value)) continue;
      if (attr.namespaceURI && !(attr.namespaceURI === XLINK_NS && name === 'href')) fail('SVG 徽章包含不支持的命名空间。');
      if (/^on/i.test(name) || !ATTRIBUTES.has(name)) fail(`SVG 徽章不支持属性“${name}”，请使用简单的静态 SVG。`);
      if (name === 'id') {
        if (!ID.test(value) || ids.has(value)) fail('SVG 徽章的图形 ID 无效或重复。');
        ids.set(value, node);
      } else if (name === 'href') {
        if (!/^#[A-Za-z_][A-Za-z0-9_.:-]*$/.test(value) || !/Gradient$/.test(node.localName)) fail('SVG 徽章不支持外部链接或嵌入图片。');
        references.push({ owner: node, id: value.slice(1), property: 'href' });
      } else if (name === 'style') {
        if (/[{}]|\/\*|\*\//.test(value)) fail('SVG 徽章请使用简单的内联样式。');
        const declarations = [];
        for (const declaration of value.split(';').filter(item => item.trim())) {
          const separator = declaration.indexOf(':');
          const property = declaration.slice(0, separator).trim().toLowerCase();
          const content = declaration.slice(separator + 1).trim();
          if (separator < 1 || !STYLE_PROPERTIES.has(property) || !content || /!important/i.test(content)) fail('SVG 徽章包含不支持的样式，请使用填色、描边、渐变或文字样式。');
          valueReferences(content, node, property);
          declarations.push(`${property}:${content}`);
        }
        node.setAttribute('style', declarations.join(';'));
      } else {
        valueReferences(value, node, name);
      }
      if (name === 'd' || name === 'points') {
        pathTokens += (value.match(/[A-Za-z]|[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?/g) || []).length;
        if (pathTokens > 50000) fail('SVG 徽章路径过于复杂，请简化后再上传。');
      }
    }
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === 1) visit(child, depth + 1);
      else if (child.nodeType === 8) node.removeChild(child);
      else if (child.nodeType !== 3 && child.nodeType !== 4) fail('SVG 徽章包含不支持的内容。');
    }
  }
  visit(root, 0);

  const dependencies = new Map(nodes.map(node => [node, new Set()]));
  for (const reference of references) {
    const target = ids.get(reference.id);
    if (!target) fail(`SVG 徽章引用了不存在的图形“${reference.id}”。`);
    const expected = reference.property === 'clip-path' ? ['clipPath'] : reference.property === 'mask' ? ['mask'] : ['linearGradient', 'radialGradient'];
    if (!expected.includes(target.localName)) fail('SVG 徽章的渐变或遮罩引用格式不正确。');
    for (let owner = reference.owner; owner; owner = owner.parentElement) dependencies.get(owner)?.add(target);
  }
  const visiting = new Set();
  const visited = new Set();
  function checkCycles(node, depth) {
    if (visiting.has(node) || depth > 32) fail('SVG 徽章不能包含循环引用或过长的图形引用。');
    if (visited.has(node)) return;
    visiting.add(node);
    for (const dependency of dependencies.get(node) || []) checkCycles(dependency, depth + 1);
    visiting.delete(node);
    visited.add(node);
  }
  for (const node of nodes) checkCycles(node, 0);

  const viewBox = root.getAttribute('viewBox');
  if (viewBox) {
    const values = viewBox.trim().split(/[\s,]+/).map(Number);
    if (values.length !== 4 || values.some(value => !Number.isFinite(value) || Math.abs(value) > 1000000) || values[2] <= 0 || values[3] <= 0) fail('SVG 徽章的 viewBox 格式不正确。');
  }
  for (const dimension of ['width', 'height']) {
    const value = root.getAttribute(dimension);
    if (!value || (viewBox && /^\d+(?:\.\d+)?%$/.test(value))) root.setAttribute(dimension, '512');
    else if (!checkDimension(value)) fail('SVG 徽章宽高需为 1–4096 的像素值，推荐 512 × 512。');
  }
  if (!viewBox) root.setAttribute('viewBox', `0 0 ${parseFloat(root.getAttribute('width'))} ${parseFloat(root.getAttribute('height'))}`);
  root.setAttribute('xmlns', SVG_NS);
  const bytes = new TextEncoder().encode(new XMLSerializer().serializeToString(root));
  if (bytes.length > MAX_BYTES) fail('SVG 徽章不能超过 2MB。');
  return `data:image/svg+xml;base64,${encodeBase64(bytes)}`;
}

/** Accept complete SVG, optionally wrapped in one Markdown svg/xml code fence. */
export function svgToBadgeImage(text) {
  let source = String(text || '').trim();
  const fenced = source.match(/^```(?:svg|xml)?\s*\r?\n([\s\S]*?)\r?\n```$/i);
  if (fenced) source = fenced[1].trim();
  if (!source) fail('请先粘贴 SVG 徽章代码。');
  return sanitizeSVG(source);
}

/** Validate persisted images. SVG is sanitized again; render the result with <img>. */
export function normalizeBadgeImage(source) {
  const value = typeof source === 'string' ? source.trim() : '';
  if (!value) return '';
  const match = value.match(DATA_IMAGE);
  if (!match) fail('徽章图片仅支持 PNG、JPG、WebP 或 SVG 格式。');
  const bytes = base64Bytes(match[2]);
  if (match[1].toLowerCase() === 'svg+xml') return sanitizeSVG(decodeUTF8(bytes));
  return `data:image/${match[1].toLowerCase()};base64,${match[2]}`;
}

export function isBadgeImage(source) {
  try { return !!normalizeBadgeImage(source); } catch { return false; }
}

export async function readBadgeImage(file) {
  if (!file || !file.size) fail('请选择有效的徽章图片。');
  if (file.size > MAX_BYTES) fail('徽章图片不能超过 2MB。');
  const svg = file.type?.toLowerCase() === 'image/svg+xml' || /\.svg$/i.test(file.name || '');
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (svg) return sanitizeSVG(decodeUTF8(bytes));
  const type = file.type?.toLowerCase();
  const extension = (file.name || '').split('.').pop().toLowerCase();
  const format = ({ 'image/png': 'png', 'image/jpeg': 'jpeg', 'image/webp': 'webp' })[type] || ({ png: 'png', jpg: 'jpeg', jpeg: 'jpeg', webp: 'webp' })[extension];
  if (!format) fail('徽章图片仅支持 PNG、JPG、WebP 或 SVG 格式。');
  const source = normalizeBadgeImage(`data:image/${format};base64,${encodeBase64(bytes)}`);
  await new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => image.naturalWidth && image.naturalHeight ? resolve() : reject(new Error('徽章图片无法读取，请重新上传。'));
    image.onerror = () => reject(new Error('徽章图片无法读取，请重新上传。'));
    image.src = source;
  });
  return source;
}
