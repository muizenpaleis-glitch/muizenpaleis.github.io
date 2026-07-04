# Finance Cockpit — Project Context

## What this is

A single-file household finance dashboard (`finance_cockpit.html`) built for a Dutch household. No backend, no build toolchain — everything runs in the browser with data stored in `localStorage`. Charts use Chart.js, CSV parsing uses PapaParse, styling uses Tailwind CDN.

**Live branch:** `claude/finance-cockpit-dashboard-uklypd`
**Repo:** `muizenpaleis-glitch/muizenpaleis.github.io`

---

## Source data

Three original documents were provided at project start — all still cached in the session uploads:

| File | Contents |
|---|---|
| `94035664-Jaarbegroting.csv` | Full annual budget with per-category monthly amounts |
| `b823754a-mjp.xlsx` | Multi-year projection (MJP) with incidental projects per year |
| ASN Bank CSV | First real bank export (May 2026 transactions) |

**ASN Bank CSV format:** 20-field, single-quoted, Dutch locale. Custom parser in the dashboard; no PapaParse default config.

---

## Key financial constants (baked into the code)

```javascript
const RECURRING_INCOME_BUDGET  = 101699;       // annual
const RECURRING_SPEND_BUDGET   = 63336.80;     // annual
const MONTHLY_RECURRING_BUDGET = 5278.07;      // spend / 12
const MONTHLY_INCOME_BUDGET    = 8474.92;      // income / 12

// MJP operational result per year (from the sheet — authoritative for the plan line)
const OP_RESULT = { 2026: 21741.24, 2027: 6250.18, 2028: 8779.56, 2029: 22996.31, 2030: 25044.96, 2031: 27037.93 };

// Annual investment injections
const INVESTMENTS = { 2026: 11300, 2027: 11526, ..., 2031: 11526 };

const PLAN_START_NET_WORTH  = 34079;   // net worth at 31-12-2025
const CRITICAL_THRESHOLD    = 15000;
const PROJECTION_START_YEAR = 2026;
```

---

## Transaction classification

Every transaction gets one of four classes via `effective(t)` (auto-classification + manual overrides stored in `localStorage`):

| Class | Meaning |
|---|---|
| `recurring` | Normal monthly spend/income — counted against the monthly budget |
| `yearly` | Annual one-offs (Vakantie, verzekeringen, etc.) — kept out of monthly budget |
| `incidental` | One-off projects from the MJP — tracked against project budgets |
| `exclude` | Internal transfers (savings, investments, own accounts) |

**Auto-classification rules:**
- Transfers to/from own accounts → `exclude`
- Bank category = *Vakantie* → `yearly` (project: Vakanties)
- Large amount + home-improvement keyword or category → `incidental`
- Everything else → `recurring`

Manual overrides are saved in `localStorage` under `fc.overrides.v1`.

---

## Budget model

```
Recurring income (€101,699)
− Recurring spend  (€63,337)
= Gross worth      (€38,362)
− Yearly one-offs  (€17,431)
− Incidentals      (€26,931)  ← MJP per year
= Net result
+ Start net worth  (€34,079)
= Net worth year-end
− Invested capital
= Household buffer (liquid)
```

**MJP projection formula:**
`NW_y = NW_{y-1} + op_result_y − investments_y − plannedIncidentals_y`

The plan line uses `OP_RESULT[]` (from the sheet). Actuals deviate by the loaded months' real income/spend vs budget.

---

## Net worth panel

Three additive pots (no double-counting):

1. **Household buffer** — derived from imports: `startNetWorth + (income − spend − yearly − incidentals) − investedCapital`
2. **Personal savings** — manual entry (saved to settings)
3. **Investment value** — manual entry (market value, saved to settings)

**Critical:** The buffer formula is shared via `computeBufferActual(agg)` between the net-worth panel and the Budget Framework's "of which buffer" line. They are guaranteed to show the same number.

---

## Spend treatment — all three views are NET (refunds subtract)

| View | Scope |
|---|---|
| Spend by bank category (pie) | Net recurring spend per category |
| Yearly recurring tracker | Net spend per item (refunds reduce it) |
| Incidental projects tracker | Net spend per project (refunds reduce it) |

---

## Default category budgets (from the Jaarbegroting)

Pre-loaded from the budget sheet — no manual entry needed. The bank's categories are coarser than the budget's, so some lines are rolled up:

| Bank category | €/month | Source lines |
|---|---|---|
| Boodschappen | 500 | Boodschappen |
| Eten & drinken | 210 | Bars 25 + Restaurants 150 + Lunch 35 |
| Huur & hypotheek | 2,175 | Hypotheek |
| Gas water & licht | 286 | Energie 260 + Water 26 |
| Internet TV & Bellen | 50 | Internet 25 + Spotify 18 + NLZiet 7 |
| Verzekeringen | 150 | All 7 insurance lines |
| Vervoer | 100 | Vervoer 50 + Parkeren 13 + Wegenbelasting 22 + OV 16 |
| Kinderen | 682 | Kinderopvang 524 + babykosten 158 |
| Huishouden & elektronica | 267 | Huis & Tuin 44 + Schoonmaak 140 + Online winkelen 83 |
| Hobby sport & vrije tijd | 91 | Kicksfit 45 + Sportschool 46 |
| Zak- & kleedgeld | 500 | Zak- & kleedgeld |
| Verzorging & gezondheid | 29 | Medisch + Cosmetica + Apotheek |
| Cadeaus | 75 | Cadeau's |
| Goede doelen | 125 | Goede doelen |
| Lening | 148 | Duurzaamheidslening 65 + Lendahand 83 |
| Klussen & onderhoud | 35 | Overig huis en tuin |
| Bankkosten | 4 | ASN bankkosten |

User can override any of these in the dashboard under **Monthly category budgets → Edit budgets**. Overrides are saved in `settings.categoryBudgets` (localStorage).

---

## Incidental projects (DEFAULT_PROJECTS)

23 items from the MJP xlsx, each with `name`, `budget`, `year`, `done` fields. Key ones:

- Belastingreservering Suus (€6,300, 2026)
- Warmtepomp (€11,000, 2026)
- Nieuwe badkamer (€12,000, 2027)
- Nieuwe auto (€30,000, 2030)
- Dakkapel (€15,000, 2031)
- Onvoorzien {year} (€2,000 each year 2026–2031)

When a project is marked **done**, the plan uses actual spend instead of the budget for that project.

---

## Yearly recurring items (DEFAULT_YEARLY — 7 items, €17,431/yr total)

| Item | Annual budget |
|---|---|
| Vakanties | €8,051 |
| Uitjes en activiteiten | €1,500 |
| Schilderwerk huis | €1,200 |
| Gemeentelijke belastingen | €1,700 |
| Auto onderhoud | €500 |
| Zorgverzekering | €2,980 |
| Overige onderhoud huis | €1,500 |

---

## localStorage keys

```javascript
const LS_KEYS = {
  settings:  'fc.settings.v2',
  tx:        'fc.transactions.v1',
  overrides: 'fc.overrides.v1',
  projects:  'fc.projects.v2',
  yearly:    'fc.yearly.v1',
  picnic:    'fc.picnic.v1'
};
```

---

## Settings object (DEFAULT_SETTINGS)

```javascript
{
  startNetWorth: 34079,
  returnRate: 0,               // % beyond 2031
  horizon: 15,                 // projection years
  savingsGrowth: 2,
  monthlyBudget: 5278.07,
  monthlyIncome: 8474.92,
  threshold: 200,              // €200 = incidental vs recurring cutoff
  savingsAccounts: ['NL16ASNB8851233608'],
  investmentAccounts: [],
  savingsIncidentalThreshold: 1500,
  projView: 'multi',           // 'multi' | 'ytd'
  incYear: 'all',
  yrYear: 'all',
  catMonth: 'latest',
  categoryBudgets: {},         // user overrides; defaults come from DEFAULT_CATEGORY_BUDGETS
  incExpanded: false, yrExpanded: false, savExpanded: false,
  catBudExpanded: false, pcExpanded: false,
  personalSavings: 0,
  investmentValue: 0
}
```

---

## Sections in the dashboard (top to bottom)

1. **KPI tiles** — net worth, monthly spend, monthly income, projected end-of-horizon
2. **Net worth — complete picture** — buffer + personal savings + investment value
3. **Budget Framework** — budgeted roll-up vs actuals (same-year, PROJECTION_START_YEAR)
4. **Net worth projection chart** — multi-year MJP (plan vs actual) or YTD cashflow view
5. **Spend by bank category** — doughnut, net recurring only
6. **Monthly cashflow** — bar chart, net recurring only
7. **Monthly category budgets** — per-category spend vs Jaarbegroting budget, month picker
8. **Picnic grocery breakdown** — item-level detail from Picnic order export
9. **Incidental projects** — collapsible, with year filter
10. **Yearly recurring** — collapsible, with year filter and budget editor
11. **Savings & investments** — savings movements, investment injections
12. **Transaction triage** — full table with manual override controls
13. **Ask your numbers** — floating analyst chat widget (keyword-based, local)

---

## Collapsible sections

HTML pattern:
```html
<button class="disc-btn" data-target="section-id" data-key="settingsKey">
  Label <span class="caret">▾</span>
</button>
<div id="section-id" class="hidden">...</div>
```

JS toggles the `hidden` class and persists open/closed state to `settings[data-key]`.

---

## Picnic grocery export tool

Located in `picnic/picnic_export.py` — a local Python 3 script (no pip dependencies) that logs into the Picnic storefront API, pulls full order history with line items, and writes `picnic_export.json`.

**Why local:** Picnic has no official API; the unofficial storefront API is CORS-locked, so the browser can't call it. Credentials never leave the user's machine.

**Recommended usage (Codespaces):**
```bash
cd picnic
cp .env.example .env     # then paste credentials into .env in the editor
python3 picnic_export.py --api-version 17
```

Then download `picnic_export.json` from Codespaces and load it in the dashboard via **Picnic grocery breakdown → Load Picnic export**.

**Known issues as of this session:**
- API version: `17` appears more reliable than the default `15`; may need further tuning if Picnic updates their API
- Login payload uses `client_id: 1` (not the header's `30100`)

---

## Parked / future work

- **Year-end rollover** — per-year budget table, anchor settings, one-click "Close year → roll forward" button. Parked until closer to December 2026.
- **Dated net-worth snapshots** — user chose current-values-only for now.
- **Picnic `--api-version` stabilisation** — needs live testing to confirm which version works.
