# uptime-pulse

A tiny serverless monitor that runs on GitHub Actions. It polls an endpoint about once a minute and sends push alerts to my phone through [ntfy](https://ntfy.sh). Alerts repeat until I acknowledge them from the notification.

- No servers, no dependencies: one Python file plus a cron workflow
- Targets and the alert channel come from repository secrets, not from the code
- State is committed back to the repo, so alerts survive between runs
- Alerts repeat every minute until acknowledged, then stop

## Setup

1. Subscribe to an ntfy topic on your phone.
2. Add the repository secrets `NTFY_TOPIC` and `WATCH_CONFIG` (JSON; see `pulse.py`).
3. Run the workflow once with **test** checked to confirm alerts arrive.
