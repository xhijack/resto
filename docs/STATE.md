# Resto Backend — Current State

> **Baca dulu sebelum mulai kerja.** Target ≤ 60 baris. Detail business rule
> ada di `PRD.md` & `context/*.md` (baca on-demand). Update file ini
> setelah commit signifikan.

## Current Focus
Stabilisasi printing & end-day flow. Belum ada feature baru aktif.

## In Progress
- _kosong_

## Pending Deploy (action user)
- [ ] `bench --site maystar.dev restart` untuk pickup commit `d215b3c` (printing cut feed 3→8) — branch `version-2` sudah pushed, belum di-bench restart prod

## Next Up (prioritas)
1. Investigate Sales Report "takeaway belum paid" — kemungkinan data leftover dari draft invoice yang tidak ter-submit (sebelum mobile v1.2.42 fix takeaway auto-logout). Validasi via query langsung DB sebelum touch kode.
2. Integration test Phase 4 — regression coverage 6 file: move-item, merge-table, void, payment, update-table-status, kitchen-printing (lihat `context/integration-tests.md`)
3. Backlog: 6 duplicate endpoint `api.py` ↔ `order.py` (dari memory sopwer_booking, tapi pattern bisa sama)

## Blockers
- Tidak ada saat ini

## Recent Changes (latest 3)
- `ead19e6` 2026-05-20 docs(readme): rewrite as authoritative landing
- `c228d72` 2026-05-20 docs: add PRD + system context docs (Phase 1)
- `d215b3c` 2026-05-18 fix(printing): pre-cut feed 3→8 di shift & end-day report

## Last Update
2026-05-20 by ramdani (Phase 4 docs: ONBOARDING + PR template) — SHA pending commit ini

## Pointers
- New here? → baca `CLAUDE.md` + `PRD.md` (sistem lengkap)
- Bug fix? → `context/<topic>.md` sesuai area (payment-flow/kitchen-flow/printing/reporting)
- Touching endpoint? → cek `context/cross-repo.md` untuk dampak ke mobile
- Mobile consumer state → `mobile-apps/sopwer-resto-pos/docs/STATE.md`
