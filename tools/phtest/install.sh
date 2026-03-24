#!/bin/bash
# phtest installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/PostHog/posthog/master/tools/phtest/install.sh | sh

set -euo pipefail

REPO="PostHog/posthog"
RELEASE_TAG="phtest-latest"

main() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"

    case "$OS" in
        Linux)  os="linux" ;;
        Darwin) os="darwin" ;;
        *)
            echo "Error: unsupported OS: $OS" >&2
            exit 1
            ;;
    esac

    case "$ARCH" in
        x86_64|amd64)  arch="amd64" ;;
        arm64|aarch64) arch="arm64" ;;
        *)
            echo "Error: unsupported architecture: $ARCH" >&2
            exit 1
            ;;
    esac

    BINARY="phtest-${os}-${arch}"
    URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${BINARY}"

    # Determine install directory
    if [ -w /usr/local/bin ]; then
        INSTALL_DIR="/usr/local/bin"
    elif [ -d "$HOME/.local/bin" ]; then
        INSTALL_DIR="$HOME/.local/bin"
    else
        mkdir -p "$HOME/.local/bin"
        INSTALL_DIR="$HOME/.local/bin"
    fi

    CHECKSUMS_URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/checksums.txt"
    TMPDIR="$(mktemp -d)"
    trap 'rm -rf "$TMPDIR"' EXIT

    echo "Downloading phtest for ${os}/${arch}..."
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$URL" -o "${TMPDIR}/phtest"
        curl -fsSL "$CHECKSUMS_URL" -o "${TMPDIR}/checksums.txt"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${TMPDIR}/phtest" "$URL"
        wget -qO "${TMPDIR}/checksums.txt" "$CHECKSUMS_URL"
    else
        echo "Error: curl or wget is required" >&2
        exit 1
    fi

    # Verify checksum
    EXPECTED=$(grep -F " ${BINARY}" "${TMPDIR}/checksums.txt" | awk '{print $1}' || true)
    if [ -z "$EXPECTED" ]; then
        echo "Error: no checksum found for ${BINARY}" >&2
        exit 1
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        ACTUAL=$(sha256sum "${TMPDIR}/phtest" | awk '{print $1}')
    elif command -v shasum >/dev/null 2>&1; then
        ACTUAL=$(shasum -a 256 "${TMPDIR}/phtest" | awk '{print $1}')
    else
        echo "Warning: cannot verify checksum (sha256sum/shasum not found), skipping" >&2
        ACTUAL="$EXPECTED"
    fi
    if [ "$ACTUAL" != "$EXPECTED" ]; then
        echo "Error: checksum mismatch (expected ${EXPECTED}, got ${ACTUAL})" >&2
        exit 1
    fi

    cp "${TMPDIR}/phtest" "${INSTALL_DIR}/phtest"
    chmod +x "${INSTALL_DIR}/phtest"

    echo "Installed phtest to ${INSTALL_DIR}/phtest"
    "${INSTALL_DIR}/phtest" --version

    # Warn if install dir is not in PATH
    case ":$PATH:" in
        *":${INSTALL_DIR}:"*) ;;
        *)
            echo ""
            echo "Note: ${INSTALL_DIR} is not in your PATH."
            echo "Add it with: export PATH=\"${INSTALL_DIR}:\$PATH\""
            ;;
    esac
}

main
