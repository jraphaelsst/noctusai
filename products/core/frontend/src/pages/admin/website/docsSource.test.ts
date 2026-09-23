import { describe, expect, it } from 'vitest';

import {
  buildDocsIndex,
  docIdToPath,
  extractTitle,
  humanizeSegment,
  loadAllDocs,
  pathToDocId,
  resolveDocLink,
  resolveImagePath,
  resolveRelativePath,
  splitHash,
  type DocsSource,
} from './docsSource';

describe('pathToDocId / docIdToPath', () => {
  it('round-trips a root doc', () => {
    expect(pathToDocId('00-index.md')).toBe('00-index');
    expect(docIdToPath('00-index')).toBe('00-index.md');
  });

  it('round-trips a nested doc', () => {
    expect(pathToDocId('03-reference-reports/linear.md')).toBe('03-reference-reports/linear');
    expect(docIdToPath('03-reference-reports/linear')).toBe('03-reference-reports/linear.md');
  });
});

describe('humanizeSegment', () => {
  it('strips a numeric prefix and title-cases dashes', () => {
    expect(humanizeSegment('03-reference-reports')).toBe('Reference Reports');
  });

  it('leaves a segment with no numeric prefix alone but title-cased', () => {
    expect(humanizeSegment('assets')).toBe('Assets');
  });
});

describe('extractTitle', () => {
  it('extracts the first H1', () => {
    expect(extractTitle('# Brief and Decisions\n\nSome body.')).toBe('Brief and Decisions');
  });

  it('ignores a heading that is not H1', () => {
    expect(extractTitle('## Not H1\n\nBody')).toBeNull();
  });

  it('returns null when there is no heading at all', () => {
    expect(extractTitle('just body text')).toBeNull();
  });
});

describe('resolveRelativePath', () => {
  it('resolves a root-doc-relative asset path unchanged', () => {
    expect(resolveRelativePath('00-index', 'assets/refs/linear-home.webp')).toBe(
      'assets/refs/linear-home.webp',
    );
  });

  it('resolves a subfolder-doc-relative ../assets path up one level', () => {
    expect(
      resolveRelativePath('03-reference-reports/linear', '../assets/refs/linear-home.webp'),
    ).toBe('assets/refs/linear-home.webp');
  });

  it('resolves a same-folder relative link', () => {
    expect(resolveRelativePath('03-reference-reports/linear', 'notion.md')).toBe(
      '03-reference-reports/notion.md',
    );
  });
});

describe('splitHash', () => {
  it('splits path + hash', () => {
    expect(splitHash('03-reference-reports/linear.md#visual-system')).toEqual({
      path: '03-reference-reports/linear.md',
      hash: 'visual-system',
    });
  });

  it('returns just the path when there is no hash', () => {
    expect(splitHash('05-information-architecture.md')).toEqual({
      path: '05-information-architecture.md',
    });
  });
});

describe('resolveDocLink', () => {
  it('resolves a same-level doc link', () => {
    expect(resolveDocLink('00-index', '05-information-architecture.md')).toEqual({
      docId: '05-information-architecture',
      hash: undefined,
    });
  });

  it('resolves a cross-folder link with a hash', () => {
    expect(
      resolveDocLink('00-index', '03-reference-reports/linear.md#visual-system'),
    ).toEqual({
      docId: '03-reference-reports/linear',
      hash: 'visual-system',
    });
  });

  it('resolves a bare in-page hash relative to the SAME doc', () => {
    expect(resolveDocLink('00-index', '#visao-geral')).toEqual({
      docId: '00-index',
      hash: 'visao-geral',
    });
  });
});

describe('resolveImagePath', () => {
  it('matches resolveRelativePath (same normalisation)', () => {
    expect(resolveImagePath('03-reference-reports/linear', '../assets/x.png')).toBe('assets/x.png');
  });
});

function fixtureSource(): DocsSource {
  return {
    markdown: {
      '00-index.md': async () => '# Índice\n\nWelcome.',
      '01-brief-and-decisions.md': async () => 'No heading here.',
      '03-reference-reports/linear.md': async () => '# Linear\n\nBody.',
      '03-reference-reports/notion.md': async () => '# Notion\n\nBody.',
    },
    images: {},
  };
}

describe('loadAllDocs', () => {
  it('loads every doc, deriving title from H1 or a humanized filename fallback', async () => {
    const entries = await loadAllDocs(fixtureSource());
    const byId = Object.fromEntries(entries.map((e) => [e.docId, e]));
    expect(byId['00-index'].title).toBe('Índice');
    expect(byId['00-index'].folder).toBeNull();
    expect(byId['01-brief-and-decisions'].title).toBe('Brief And Decisions');
    expect(byId['03-reference-reports/linear'].folder).toBe('03-reference-reports');
  });
});

describe('buildDocsIndex', () => {
  it('groups root docs first (no label), then folders alpha-sorted, entries sorted by docId', async () => {
    const entries = await loadAllDocs(fixtureSource());
    const groups = buildDocsIndex(entries);

    expect(groups[0].label).toBeNull();
    expect(groups[0].entries.map((e) => e.docId)).toEqual([
      '00-index',
      '01-brief-and-decisions',
    ]);

    expect(groups[1].label).toBe('Reference Reports');
    expect(groups[1].entries.map((e) => e.docId)).toEqual([
      '03-reference-reports/linear',
      '03-reference-reports/notion',
    ]);
  });

  it('returns no groups for an empty doc set (the empty-state trigger)', () => {
    expect(buildDocsIndex([])).toEqual([]);
  });
});
