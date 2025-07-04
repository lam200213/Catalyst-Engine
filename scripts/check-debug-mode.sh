#!/bin/bash
if grep -q "FLASK_DEBUG" "docker-compose.yml"; then
  echo "Error: FLASK_DEBUG is set in docker-compose.yml. Please remove it before committing."
  exit 1
fi
echo "Configuration check passed: FLASK_DEBUG is not set."
exit 0