# Resto Sopwer

ERPNext custom app — Point of Sale untuk restoran multi-outlet di Indonesia. Workflow dine-in & take-away, kitchen routing, atomic payment, ESC/POS receipt printing, end-day consolidated reporting.

> **This repo is the AUTHORITATIVE source of truth for the resto system.**
> Konsumen lain (mobile RN POS, future web POS, API client) refer ke sini untuk business rules, DocType model, dan endpoint contracts.

## Documentation

**Baca dulu sebelum mulai kerja**:
- [`docs/STATE.md`](docs/STATE.md) — current sprint progress, in-progress tasks, blockers
- [`CLAUDE.md`](CLAUDE.md) — short repo-level guide untuk Claude / AI assistants

**Dev baru**: mulai dari [`docs/ONBOARDING.md`](docs/ONBOARDING.md) — checklist 2-3 hari sampai produktif, urutan baca, common pitfalls.

**Onboarding & deep dive**:
- [`docs/PRD.md`](docs/PRD.md) — Product Requirements Document (15 section: roles, domain model, workflows, DocType catalog, 49 endpoint catalog, services, business rules invariants)
- [`docs/context/architecture.md`](docs/context/architecture.md) — services + repositories + events detail
- [`docs/context/payment-flow.md`](docs/context/payment-flow.md) — `pay_invoice` atomic full-pay
- [`docs/context/kitchen-flow.md`](docs/context/kitchen-flow.md) — `send_to_kitchen` + status_kitchen lifecycle
- [`docs/context/printing.md`](docs/context/printing.md) — ESC/POS cut convention
- [`docs/context/reporting.md`](docs/context/reporting.md) — `get_end_day_report_v2` shape & filter
- [`docs/context/integration-tests.md`](docs/context/integration-tests.md) — site `resto.integration_test` setup
- [`docs/context/cross-repo.md`](docs/context/cross-repo.md) — kontrak silang dengan mobile RN POS

**Consumer apps**:
- Mobile RN POS — `github.com/xhijack/sopwer-resto-pos` (branch `version-1`)

## Contributing

**Pull-before / Update-after workflow**:
```bash
git pull
cat docs/STATE.md     # baca dulu — apa sedang dikerjain, apa next
cat CLAUDE.md         # repo-level instructions
# ... kerja ...
# update docs/STATE.md kalau ada checkpoint signifikan
git add docs/STATE.md
git commit -m "docs(state): update progress"
git push
```

**Cross-repo discipline** (saat menyentuh endpoint / DocType field / status string yang dibaca mobile):
1. Update [`docs/context/cross-repo.md`](docs/context/cross-repo.md) di repo ini
2. Buka PR di mobile repo yang update `docs/context/cross-repo.md` sisi mobile
3. Merge dua-duanya bareng (ideal: sama hari)

Mismatch = invoice rusak, order hilang, atau report salah. Pernah kejadian di mobile v1.2.41 & v1.1.x — semua karena cross-repo contract tidak ter-validate.

## Tech Stack

- Framework: Frappe/ERPNext (Python)
- App name: `resto`
- Site dev: `maystar.dev`
- Branch dev: `version-2`
- Publisher: PT Sopwer Teknologi Indonesia (`ramdani@sopwer.net`)

## License

MIT
