// noc perf read — returns a slice of localStorage['__noc_perf'] (browser JS output is capped ~1 KB).
// Page through with OFFSET += SIZE until `done` is true; concatenate the `s` parts.
(() => {
  const raw = localStorage.getItem('__noc_perf') || '';
  const off = __OFFSET__, size = __SIZE__;
  return { total: raw.length, off, done: off + size >= raw.length, s: raw.slice(off, off + size) };
})();
