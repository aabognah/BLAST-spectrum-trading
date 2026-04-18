#!/bin/bash

set -euo pipefail

# Usage:
#   GOOGLE_CLOUD_PROJECT=<your-project> ./run_simulations.sh
# Optional:
#   GOOGLE_CLOUD_MODEL=gemini-2.5-flash ./run_simulations.sh

if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
	echo "ERROR: GOOGLE_CLOUD_PROJECT is not set."
	echo "Export it first, for example:"
	echo "  export GOOGLE_CLOUD_PROJECT=my-gcp-project-id"
	exit 1
fi

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

nohup bash -lc 'source venv/bin/activate && python3 -u test_scenario_1.py' > "$LOG_DIR/scenario_1.log" 2>&1 &
echo "Started Scenario 1 in background. Log: $LOG_DIR/scenario_1.log"

nohup bash -lc 'source venv/bin/activate && python3 -u test_scenario_2.py' > "$LOG_DIR/scenario_2.log" 2>&1 &
echo "Started Scenario 2 in background. Log: $LOG_DIR/scenario_2.log"
