## What

<!-- 1-3 kalimat: apa yang berubah dan kenapa -->

## Why

<!-- Konteks: bug fix link issue, feature request, refactor reason -->

## Testing

<!-- Bagaimana di-verify? Unit test? Manual? Integration test? -->

```bash
# Contoh:
# bench --site maystar.dev run-tests --app resto --module resto.tests.test_payment_service
# bench --site resto.integration_test execute resto.tests.cleanup.cleanup_test_data
```

## Checklist

- [ ] Tests pass (`bench run-tests --app resto`)
- [ ] `docs/STATE.md` di-update kalau ada checkpoint signifikan (current focus, next up, blockers)
- [ ] `docs/context/cross-repo.md` di-update kalau menyentuh:
  - [ ] Endpoint signature (`@frappe.whitelist` baru / signature berubah)
  - [ ] DocType field yang dibaca mobile (lihat tabel "DocType Field Shape" di cross-repo.md)
  - [ ] Status string convention (`order_type`, `status`, `table.status`, `status_kitchen`, dll)
- [ ] **Mirror PR di mobile repo** (`github.com/xhijack/sopwer-resto-pos`) kalau breaking change
- [ ] Conventional commit message (`feat:` / `fix:` / `refactor:` / `chore:` / `docs:`)
- [ ] No `--no-verify`, no hook skipping
- [ ] PR description menjelaskan **why**, bukan cuma **what** (kode sudah menjelaskan what)

## Cross-Repo Impact

<!-- Kalau breaking ke mobile, link mirror PR di sini. Kalau tidak breaking, "none" -->

Mirror PR: _none_ / _link_

## Deploy Notes

<!-- Action user pasca-merge? mis. "User harus `bench --site <site> restart` untuk pickup ini." -->
