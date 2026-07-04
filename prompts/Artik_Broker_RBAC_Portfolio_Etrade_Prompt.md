# Artik Broker — Role-Based Access + Portfolio/E*TRADE Integration

Update artik_broker role-based access and Portfolio/E*TRADE integration.

## Requirements

1. Add simple role-based access control.
   - Add a role field to users.
   - Give username "admin" the role "admin".
   - Default all other users to role "user".
   - Existing login behavior should continue to work.

2. Sidebar visibility:
   - Only users with role "admin" can see:
     - E*TRADE left menu item
     - Portfolio left menu item
   - Non-admin users must not see or access these pages directly by URL.

3. Portfolio page:
   - Keep the existing Excel upload portfolio workflow unchanged.
   - Keep existing snapshot dropdown.
   - Add an additional dropdown/filter for portfolio source:
     - Uploaded Excel
     - E*TRADE
   - Show E*TRADE-created snapshots in the same existing Portfolio page.

4. E*TRADE Analyze button:
   - On the E*TRADE holdings page, keep existing functionality unchanged.
   - Add/keep "Analyze Portfolio".
   - When clicked, create a portfolio snapshot from the currently selected E*TRADE account holdings.
   - Save account ending, holdings, timestamp, total market value, total gain/loss, and source = "E*TRADE".
   - Redirect or open the existing Portfolio page.
   - Auto-select the newly created E*TRADE snapshot in the Portfolio dropdown.

5. Analysis behavior:
   - When an E*TRADE snapshot is selected, populate the Portfolio page using the E*TRADE holdings data.
   - Use the same existing portfolio analysis flow already used for uploaded Excel portfolios.
   - Do not duplicate the analysis engine.

6. Security:
   - Do not store E*TRADE tokens or credentials in portfolio snapshots.
   - Do not expose admin-only API responses to non-admin users.
   - Backend must enforce role checks, not only frontend hiding.

7. UI:
   - Match existing dark theme.
   - Keep the current Portfolio page design.
   - Add only the source dropdown and E*TRADE snapshot selection behavior.
   - Do not break desktop or mobile layout.

Deliver complete backend, database migration/init changes, frontend/sidebar changes, and route/API protection.

---

## Implementation (delivered — commits `954b3ae`, `a39226c`; deployed to AWS App Runner)

- **RBAC:** server-side gate in the `_auth_gate` middleware makes `/api/etrade*`, `/api/portfolio*`,
  and `/api/analyze_portfolio` admin-only (403 for non-admins). Sidebar hides E*TRADE / Portfolio /
  Users for non-admins; `showTab` guards them too. Role already lives on users (`admin` = admin).
- **Persistence:** `portfolio_store.py` stores snapshots in the Litestream-backed users DB
  (`portfolio_snapshots` table) — holdings/totals/account-ending/source only, **never tokens**.
- **E*TRADE → snapshot:** `POST /api/etrade/analyze` builds a snapshot from the selected account;
  "📊 Analyze Portfolio" opens the Portfolio page and auto-selects it.
- **Portfolio page:** Source dropdown (Uploaded Excel / E*TRADE); snapshots keyed `xl:<file>` | `et:<id>`.
- **Shared engine:** extracted `_score_holdings()` (from the refresh path); E*TRADE snapshots scored live
  through it — no engine duplication.
- Verified live: non-admin 403, admin 200, unauthenticated 401.
