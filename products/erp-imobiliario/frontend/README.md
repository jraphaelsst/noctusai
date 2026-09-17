# Frontend — ERP Imobiliário

React + TypeScript + Vite frontend for the ERP Imobiliário product (real estate CRM: clients, properties, sales funnels, financials).

## Setup

```bash
cd products/erp-imobiliario/frontend
npm install
```

## Run

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Test

```bash
npm run test        # vitest (unit)
npm run test:e2e    # playwright (e2e)
```

## Stack

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS

## Environment Variables

All frontends read env vars via `import.meta.env`. See `CLAUDE.md` at the repo root for the full list of required variables.

## 📘 Development Patterns

This project follows specific coding patterns to ensure consistency and best practices:

### Modal Implementation Pattern
All modals follow a standardized `formData` pattern for instant UI updates.

**Documentation**: See [KNOWLEDGE-BASE/CONTEXT/frontend/02-ERP.md](../../../KNOWLEDGE-BASE/CONTEXT/frontend/02-ERP.md) (Modal Patterns section)

**Key Rules**:
- Use `formData` state, not entity props, for display
- Update UI instantly without closing modals
- Keep consistent behavior across all modals

**Reference Implementations**:
- `src/components/modals/MetaDetalhesModal.tsx`
- `src/components/modals/UsuarioDetalhesModal.tsx`
- `src/components/modals/ConfiguracoesMetasModal.tsx`
