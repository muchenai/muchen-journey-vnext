// The supplied templates contain style attributes for badge colours, sliders
// and progress bars. Apply those same declarations through CSSOM, which works
// with the existing CSP without allowing arbitrary inline styles or scripts.
(() => {
  function apply(element) {
    if (!(element instanceof HTMLElement) || !element.hasAttribute('style')) return;
    const values = [...element.style].map(name => [name, element.style.getPropertyValue(name), element.style.getPropertyPriority(name)]);
    element.removeAttribute('style');
    for (const [name, value, priority] of values) element.style.setProperty(name, value, priority);
  }
  function visit(node) {
    if (!(node instanceof Element)) return;
    apply(node); node.querySelectorAll('[style]').forEach(apply);
  }
  new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(visit))).observe(document.documentElement, { childList: true, subtree: true });
  visit(document.documentElement);
})();
