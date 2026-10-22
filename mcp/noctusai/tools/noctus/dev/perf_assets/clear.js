// noc perf clear — drop the accumulated capture so the next session starts clean.
(() => { const had = !!localStorage.getItem('__noc_perf'); localStorage.removeItem('__noc_perf'); return { cleared: had }; })();
