// Lists every apigw call the page made since load (paths + param NAMES only).
// Works without the logger (no method/status/shape). Output avoids raw query strings,
// which the MCP output filter blocks.
[...new Set(performance.getEntriesByType('resource')
  .filter((e) => /apigw/.test(e.name))
  .map((e) => {
    const u = new URL(e.name);
    return u.pathname
      .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, 'UUID')
      .replace(/\d{5,}/g, 'ID')
      + (u.search ? ' PARAMS ' + [...new Set(u.searchParams.keys())].join(' , ') : '');
  }))].join(' ;; ');
