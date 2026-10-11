#!/usr/bin/env bash
# ==============================================================================
# Astra Desktop Automation - Uninstaller
# Stops, disables, and removes Astra systemd user services.
# ==============================================================================

set -euo pipefail

SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "Stopping Astra user services..."
systemctl --user stop \
    automation-astra.service \
    event-voice.service \
    desktop-events.service \
    advanced-events.service 2>/dev/null || true

echo "Disabling Astra user services..."
systemctl --user disable \
    automation-astra.service \
    event-voice.service \
    desktop-events.service \
    advanced-events.service 2>/dev/null || true

echo "Removing systemd unit files..."
rm -f "${SYSTEMD_USER_DIR}/automation-astra.service" \
      "${SYSTEMD_USER_DIR}/event-voice.service" \
      "${SYSTEMD_USER_DIR}/desktop-events.service" \
      "${SYSTEMD_USER_DIR}/advanced-events.service"

systemctl --user daemon-reload
systemctl --user reset-failed 2>/dev/null || true

echo "Astra services have been disabled and removed."
echo "Note: Project directory and cache files were kept intact."
