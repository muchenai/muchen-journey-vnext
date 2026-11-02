// ESLint 9 and some plugins call the pre-v9 CommonJS function export.
// Keep that API while executing only the patched minimatch 11 implementation.
// Modern consumers can still destructure .minimatch, .Minimatch and .match.
const entry = require.resolve('minimatch');
// eslint-disable-next-line @typescript-eslint/no-require-imports -- preload must update the CommonJS export before ESLint loads
const modern = require(entry);
if (typeof modern !== 'function') {
  require.cache[entry].exports = Object.assign(modern.minimatch, modern);
}
