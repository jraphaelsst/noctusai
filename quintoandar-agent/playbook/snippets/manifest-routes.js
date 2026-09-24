// Every page route the Next.js app ships (48 on 2026-09-24).
// Note: /listing/:id/:type works but is NOT in this list.
const bm = self.__BUILD_MANIFEST;
(bm ? (bm.sortedPages || Object.keys(bm).filter((k) => k.startsWith('/'))) : ['NO_MANIFEST']).join('\n');
