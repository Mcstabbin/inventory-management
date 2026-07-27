---
name: vue-component-analysis
description: Analyze Vue 3 single-file components for performance, reactivity, and reuse issues, then propose concrete fixes. Use this skill when reviewing or refactoring .vue files in client/src.
---

# Vue Component Analysis

This skill audits Vue 3 single-file components in the Factory Inventory Management app and produces a prioritized, actionable report. It encodes the conventions in `CLAUDE.md` and `client/CLAUDE.md` so every review is consistent with how the rest of the app is written.

Use it when asked to review, analyze, optimize, or refactor any `.vue` file, or before opening a PR that touches components.

## What to analyze

Read the target component(s) in full, then evaluate against the checklist below. Compare against a known-good reference component (`Dashboard.vue` or `Orders.vue`) whenever a pattern is ambiguous — the rest of the app is the style guide.

### 1. API style consistency (highest priority)
- **Composition API only.** The project mandates `setup()` + `ref`/`computed`. Flag any component using the Options API (`data()`, `methods:`, `mounted()`), and treat it as a rewrite candidate — this is the single biggest source of drift in this codebase.
- No mixing of Options and Composition API within one component.

### 2. Reactivity correctness
- Derived values must be `computed`, not recalculated imperatively in methods or lifecycle hooks.
- Raw data lives in `ref`s; never mutate a `computed`.
- No props mutation — emit events upward instead.
- Watchers reload data on the right dependencies (e.g. the global filter refs from `useFilters`).

### 3. Performance
- Template-called methods that do real work (loops, `Math.max`, formatting) run on **every render** — move them to `computed`. Flag any `v-for` row that calls such a method.
- Prefer `computed` over methods for anything derived and reused.
- Debounce high-frequency inputs (sliders, search) before firing API calls.
- Use `v-show` over `v-if` for frequently toggled, always-mounted content.

### 4. Reuse & structure
- Duplicated logic across components → extract a composable (`client/src/composables`).
- Duplicated currency/date/number formatting → use the shared `utils/currency.js` and the locale-aware helpers, not hand-rolled formatters.
- Templates over ~100 lines or logic over ~150 lines → consider extracting a child component.

### 5. Correctness & conventions (project-specific)
- **`v-for` keys** must be stable domain ids (`sku`, `month`, `id`, `quarter`) — never the array index.
- **i18n**: every user-facing string goes through `t()`. Flag hardcoded English. Currency must respect the active locale (USD/JPY).
- **Dates**: validate with `isNaN(date.getTime())` before calling `.getMonth()` etc.
- **Data loading**: `loading` / `error` / data refs with try/catch/finally, and the template must render all three states.
- **API access**: go through the shared `client/src/api.js` client, never a direct `axios` import with a hardcoded URL.
- **No debug logging**: no `console.log` in committed components (a pre-commit hook also enforces this).

## How to report

Produce a single prioritized list. For each finding include:

1. **Location** — `file:line` (clickable).
2. **Severity** — `high` (breaks a project rule or a user-visible bug), `medium` (perf / maintainability), `low` (polish).
3. **What & why** — one sentence on the problem and its impact.
4. **Fix** — the concrete change, with a short before/after snippet where it clarifies.

Order the list severity-first. End with a one-line summary: counts by severity and the single highest-impact change to make first.

### Example finding

```
client/src/views/Reports.vue:214  [high]  Performance / conventions
formatNumber() is a template-called method that runs on every cell render and
also reimplements toLocaleString by hand, ignoring the active currency.
Fix: replace with the shared currency util in a computed-friendly helper:
  - {{ formatNumber(q.total_revenue) }}
  + {{ formatMoney(q.total_revenue) }}   // formatCurrency(amount, currentCurrency)
```

## Scope discipline

- Analyze only what was asked; don't rewrite unrelated components.
- Recommendations must match existing patterns in the app — cite the reference component you compared against.
- If a `.vue` file must be created or significantly modified as a result, delegate that edit to the `vue-expert` subagent, per `CLAUDE.md`.
