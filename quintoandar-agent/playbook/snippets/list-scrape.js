// Aggregates a /status/* (or similar) list page: header text, column labels, and counts of
// the short label lines (status tags, motivos). Rows are divs, not <table>. Phones masked;
// row links stripped of query strings (the MCP output filter blocks them).
const m = document.querySelector('main');
const L = m.innerText.split('\n').map((s) => s.trim()).filter(Boolean);
const i = L.findIndex((l) => /\d+-\d+ de \d+/.test(l));
const counts = {};
L.slice(i).forEach((l) => {
  if (!/^[A-Z]{2,4}\d|^R\$|Copiar|^\d+$|^Aluguel$|^Venda$/.test(l) && !/ - /.test(l) && l.length < 120) {
    counts[l] = (counts[l] || 0) + 1;
  }
});
JSON.stringify({
  head: L.slice(0, 2),
  counter: L[i],
  columns: L.slice(i + 1, i + 7),
  counts: Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 40),
  rowLinks: [...new Set([...m.querySelectorAll('a[href]')].map((a) => a.getAttribute('href').split('?')[0].replace(/[0-9a-f-]{36}/, 'UUID').replace(/\/\d{6,}\//, '/ID/')))],
}).replace(/\(\d\d\) \d{4,5}-\d{4}/g, '(TEL)');
