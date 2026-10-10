#!/usr/bin/env bash
# Creates .env for Docker Compose with freshly generated tokens. Never overwrites an existing file.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  echo ".env already exists; leaving it unchanged."
  exit 0
fi
umask 077
cp .env.example .env
admin=$(openssl rand -hex 24)
runner=$(openssl rand -hex 24)
sed -i.bak -e "s/^FORGEFLOW_ADMIN_TOKEN=.*/FORGEFLOW_ADMIN_TOKEN=${admin}/" \
           -e "s/^FORGEFLOW_RUNNER_TOKEN=.*/FORGEFLOW_RUNNER_TOKEN=${runner}/" .env
rm -f .env.bak
echo "Created .env with new FORGEFLOW_ADMIN_TOKEN and FORGEFLOW_RUNNER_TOKEN (file mode 600)."
echo "Use the admin token for API calls: grep FORGEFLOW_ADMIN_TOKEN .env"
