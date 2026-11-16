#!/bin/sh
# deploy/electrumx-launcher.sh — ExecStart wrapper for deploy/electrumx.service.
#
# The systemd unit must name an ABSOLUTE executable path (systemd-analyze
# verify rejects "${VAR}/bin/python" as the first command word), and the
# venv/repo paths are host-specific — so they live in the env file and this
# launcher expands them with real shell semantics at exec time.
#
# Install at the fixed absolute path the unit references:
#   install -m 755 deploy/electrumx-launcher.sh /usr/local/sbin/electrumx-maza-launcher
#
# Environment (from the unit's EnvironmentFile): ELECTRUMX_VENV and
# MAZA_REPO_DIR. ${VAR:?} fails LOUDLY if either is missing — an empty
# expansion can never silently exec "/bin/python".
set -u
exec "${ELECTRUMX_VENV:?ELECTRUMX_VENV not set - check the env file}/bin/python" \
     "${MAZA_REPO_DIR:?MAZA_REPO_DIR not set - check the env file}/indexer/run_indexer.py" "$@"
