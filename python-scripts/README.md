# Python Scripts

1. 001-nginx-log-triage: we can use below command to run this script. The script reads a Common Log Format (CLF) access log, optionally restricted to entries at or after a given instant, and reports aggregate statistics in either a human-readable text format or a single-line JSON object.
`python3 001-nginx-log-triage.py --log envoy_access_log.txt --top 1 --since 2026-09-03T08:15:22.104Z --format text`

