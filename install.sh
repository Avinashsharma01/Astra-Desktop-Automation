#!/usr/bin/env bash
# ==============================================================================
# Astra Desktop Automation - Automated Installer
# Installs dependencies, sets up Python venv, downloads TTS models, and
# configures systemd user services for Astra Desktop Automation.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/Automation"
VENV_DIR="${SCRIPT_DIR}/piper-venv"
MODELS_DIR="${SCRIPT_DIR}/tts-models"
CACHE_DIR="${SCRIPT_DIR}/tts-cache"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

MODEL_NAME="en_US-amy-medium"
ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx"
JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json"

echo "======================================================"
echo "    Astra Desktop Automation - Setup & Installation    "
echo "======================================================"

# 1. Check & Install System Packages (Debian / Ubuntu)
if command -v apt-get >/dev/null 2>&1; then
    echo "[1/6] Checking system package requirements..."
    PKGS_TO_INSTALL=()
    for pkg in python3 python3-venv python3-pip mpv curl rfkill network-manager bluez; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            PKGS_TO_INSTALL+=("$pkg")
        fi
    done

    if [ ${#PKGS_TO_INSTALL[@]} -gt 0 ]; then
        echo "Installing missing packages: ${PKGS_TO_INSTALL[*]}"
        sudo apt-get update
        sudo apt-get install -y "${PKGS_TO_INSTALL[@]}"
    else
        echo "All required system packages are already installed."
    fi
else
    echo "[1/6] Warning: Non-apt system detected. Ensure python3, mpv, and network-manager are installed."
fi

# 2. Setup Python Virtual Environment
echo "[2/6] Setting up Python virtual environment in ${VENV_DIR}..."
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip
if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
    "${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
else
    "${VENV_DIR}/bin/pip" install psutil pyudev piper-tts
fi

# 3. Download TTS Model if missing
echo "[3/6] Verifying Piper TTS voice models..."
mkdir -p "${MODELS_DIR}"
if [ ! -f "${MODELS_DIR}/${MODEL_NAME}.onnx" ]; then
    echo "Downloading ${MODEL_NAME}.onnx from Hugging Face..."
    curl -L -o "${MODELS_DIR}/${MODEL_NAME}.onnx" "${ONNX_URL}"
fi
if [ ! -f "${MODELS_DIR}/${MODEL_NAME}.onnx.json" ]; then
    echo "Downloading ${MODEL_NAME}.onnx.json..."
    curl -L -o "${MODELS_DIR}/${MODEL_NAME}.onnx.json" "${JSON_URL}"
fi

# 4. Make scripts executable and warm voice cache
echo "[4/6] Initializing voice cache..."
chmod +x "${SCRIPT_DIR}"/events.py "${SCRIPT_DIR}"/scripts/*.py "${SCRIPT_DIR}"/bin/*
mkdir -p "${CACHE_DIR}"

"${VENV_DIR}/bin/python" "${SCRIPT_DIR}/scripts/warm-voice-cache.py" || true

# 5. Install systemd user services
echo "[5/6] Installing systemd user services..."
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${SCRIPT_DIR}/systemd/"*.service "${SYSTEMD_USER_DIR}/"

systemctl --user daemon-reload
systemctl --user enable \
    automation-astra.service \
    event-voice.service \
    desktop-events.service \
    advanced-events.service

# 6. Start the services
echo "[6/6] Starting Astra services..."
systemctl --user restart \
    automation-astra.service \
    event-voice.service \
    desktop-events.service \
    advanced-events.service

echo "======================================================"
echo "  Astra Desktop Automation successfully installed!    "
echo "  Live status:"
systemctl --user is-active \
    automation-astra.service \
    event-voice.service \
    desktop-events.service \
    advanced-events.service
echo "======================================================"
echo "To view live logs: journalctl --user -f -u desktop-events.service"
