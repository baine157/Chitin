# CoS Ops Dashboard

Local read-only Chief of Staff observability surface. This slice is dependency
free: plain HTML, CSS, and JavaScript under `ui/ops-dashboard/`.

Optional data refresh if the generator is present:

```bash
python3 scripts/observability/collect_dashboard.py
```

Serve from repo root:

```bash
python3 -m http.server 4177 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:4177/ui/ops-dashboard/
```

The dashboard reads `/state/observability/dashboard.json` or
`../../state/observability/dashboard.json` when served from the repo root. If
neither path is available, it renders embedded sample data instead.

## Desktop App (Double-Click)

Install launcher + desktop icon:

```bash
chmod +x scripts/observability/launch_ops_dashboard_app.sh \
  scripts/observability/install_ops_dashboard_desktop_entry.sh
scripts/observability/install_ops_dashboard_desktop_entry.sh
```

Then double-click:

`~/Desktop/CoS Ops Dashboard.desktop`

What it does on launch:
- Refreshes `state/observability/dashboard.json`
- Starts local server on `127.0.0.1:4177` if needed
- Opens an app-style browser window at `/ui/ops-dashboard/`

Auto-refresh behavior:
- Dashboard auto-refreshes every 5 seconds by default
- Optional override in URL: `?refreshSec=15` or `?refreshMs=15000`
