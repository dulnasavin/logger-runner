from pathlib import Path


path = Path(".github/workflows/crypto_runner.yml")
text = path.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    "# CRYPTO PRICE LOGGER - PRODUCTION S1.5\n# NETWORK SELF-HEALING + THREE-SOURCE PRICE CONSENSUS",
    "# CRYPTO PRICE LOGGER - PRODUCTION S2\n# BOUNDED NETWORK RECOVERY + THREE-SOURCE PRICE CONSENSUS",
    "header",
)
replace_once(
    "# - Recovery receives exactly one complete VPN1/VPN2 retry.\n# - VPN1 and VPN2 must prove different public exit IPs.",
    "# - VPN1 is the primary collection network; VPN2 is validated as cold standby.\n# - Transient VPN1 startup failures receive one bounded retry, then one VPN2 failover.",
    "startup policy comments",
)
replace_once(
    "# - Provider-triggered VPN switching is NOT wired yet in S1.",
    "# - Provider-triggered recovery is enabled with one global VPN2 switch ceiling.",
    "provider recovery comment",
)

replace_once(
    '            "$LOGGER_DIR/network_manager.py" \\\n            "$LOGGER_DIR/requirements.lock" \\',
    '            "$LOGGER_DIR/network_manager.py" \\\n            "$LOGGER_DIR/s2_network_manager.py" \\\n            "$LOGGER_DIR/provider_network_recovery.py" \\\n            "$LOGGER_DIR/vpn_profile_normalizer.py" \\\n            "$LOGGER_DIR/requirements.lock" \\',
    "required S2 files",
)
replace_once(
    '            "$LOGGER_DIR/network_manager.py" \\\n            "$RECOVERY_DIR/recovery_controller.py" \\',
    '            "$LOGGER_DIR/network_manager.py" \\\n            "$LOGGER_DIR/s2_network_manager.py" \\\n            "$LOGGER_DIR/provider_network_recovery.py" \\\n            "$LOGGER_DIR/vpn_profile_normalizer.py" \\\n            "$RECOVERY_DIR/recovery_controller.py" \\',
    "compile S2 files",
)

start_marker = """      # ======================================================================
      # SECTION 16 - RESET AND VALIDATE NETWORK MANAGER
"""
end_marker = """      # ======================================================================
      # SECTION 23 - RECORD PRODUCTION CSV STATE BEFORE LOGGER
"""
if text.count(start_marker) != 1 or text.count(end_marker) != 1:
    raise SystemExit("network integration markers are missing or ambiguous")
start = text.index(start_marker)
end = text.index(end_marker)
if end <= start:
    raise SystemExit("network integration markers are out of order")

new_network_block = """      # ======================================================================
      # SECTION 16 - PREPARE S2 NETWORK MANAGER RUNTIME
      # ======================================================================
      - name: "16.1 Prepare S2 network runtime boundary"
        env: &network_env
          NETWORK_MANAGER_STATE_DIR: ${{ runner.temp }}/network-manager
          NETWORK_MANAGER_ALLOWED_ROOTS: ${{ runner.temp }}:${{ github.workspace }}
          VPN1_CONFIG: ${{ runner.temp }}/vpn-runtime/vpn1.ovpn
          VPN1_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn1-auth.txt
          VPN2_CONFIG_FILE: ${{ runner.temp }}/vpn-runtime/vpn2.ovpn
          VPN2_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn2-auth.txt
        run: |
          set -euo pipefail
          test -s "private_logger/Crypto Logger-Private Repo/s2_network_manager.py"
          test -s "private_logger/Crypto Logger-Private Repo/provider_network_recovery.py"
          test -s "private_logger/Crypto Logger-Private Repo/vpn_profile_normalizer.py"
          test -s "$VPN1_CONFIG"
          test -s "$VPN1_AUTH_FILE"
          test -s "$VPN2_CONFIG_FILE"
          test -s "$VPN2_AUTH_FILE"
          echo "✅ S2 Network Manager is ready before any network-sensitive provider work"

      # ======================================================================
      # SECTION 18 - BOOTSTRAP VPN1 + AUTH RECOVERY + COLD-STANDBY VPN2
      # ======================================================================
      - name: "18.1 Bootstrap managed network and recover VPNBook auth if required"
        id: vpn_auth_recovery
        env:
          NETWORK_MANAGER_STATE_DIR: ${{ runner.temp }}/network-manager
          NETWORK_MANAGER_ALLOWED_ROOTS: ${{ runner.temp }}:${{ github.workspace }}
          VPN1_CONFIG: ${{ runner.temp }}/vpn-runtime/vpn1.ovpn
          VPN1_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn1-auth.txt
          VPN2_CONFIG_FILE: ${{ runner.temp }}/vpn-runtime/vpn2.ovpn
          VPN2_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn2-auth.txt
          VPN_SECRET_UPDATE_TOKEN: ${{ secrets.VPN_SECRET_UPDATE_TOKEN }}
        run: |
          set -euo pipefail
          CONTROLLER="private_logger/Crypto Logger-Private Repo/vpn_auth_recovery/recovery_controller.py"
          python "$CONTROLLER" \\
            --state-dir "$NETWORK_MANAGER_STATE_DIR" \\
            --vpn1-config "$VPN1_CONFIG" \\
            --vpn1-auth "$VPN1_AUTH_FILE" \\
            --vpn2-config "$VPN2_CONFIG_FILE" \\
            --vpn2-auth "$VPN2_AUTH_FILE" \\
            --self-test-output "${RUNNER_TEMP}/s2-bootstrap.json" \\
            --recovered-marker "${RUNNER_TEMP}/vpn-auth-recovered" \\
            --recovery-failed-marker "${RUNNER_TEMP}/vpn-auth-recovery-failed" \\
            --secret-update-success-marker "${RUNNER_TEMP}/vpn-secret-update-success" \\
            --secret-update-failed-marker "${RUNNER_TEMP}/vpn-secret-update-failed" \\
            --repository "$GITHUB_REPOSITORY" \\
            --persist-secrets \\
            --update-vpn2-secrets

      # ======================================================================
      # SECTION 19 - VERIFY THE MANAGED STARTUP NETWORK
      # ======================================================================
      - name: "19.1 Verify S2 bootstrap and bounded network state"
        env: *network_env
        run: |
          set -euo pipefail
          BOOTSTRAP="${RUNNER_TEMP}/s2-bootstrap.json"
          STATUS="${RUNNER_TEMP}/network-manager-status.json"
          test -s "$BOOTSTRAP"
          jq -e '
            .passed == true and
            .vpn2_standby_validated == true and
            (.startup_network == "VPN1" or .startup_network == "VPN2")
          ' "$BOOTSTRAP" >/dev/null
          STARTUP_NETWORK="$(jq -r '.startup_network' "$BOOTSTRAP")"
          echo "STARTUP_NETWORK=$STARTUP_NETWORK" >> "$GITHUB_ENV"
          python "private_logger/Crypto Logger-Private Repo/s2_network_manager.py" status | tee "$STATUS"
          grep -q '"running": true' "$STATUS"
          SWITCH_COUNT="$(jq -r '.switch_count' "$STATUS")"
          test "$SWITCH_COUNT" -le 1
          echo "✅ S2 bootstrap verified on ${STARTUP_NETWORK}; VPN2 remains cold unless recovery required"

      # ======================================================================
      # SECTION 20 - REPORT AUTH RECOVERY / SECRET UPDATE OUTCOME
      # ======================================================================
      - name: "20.1 Report VPN credential recovery state"
        run: |
          set -euo pipefail
          if [ -f "${RUNNER_TEMP}/vpn-auth-recovered" ]; then
            echo "⚠ Stored credentials expired; live VPNBook recovery succeeded"
          else
            echo "✅ Stored VPN credentials remained valid"
          fi

          if [ -f "${RUNNER_TEMP}/vpn-secret-update-success" ]; then
            echo "✅ GitHub VPN secrets updated"
          elif [ -f "${RUNNER_TEMP}/vpn-secret-update-failed" ]; then
            echo "⚠ GitHub VPN secret update failed; current run may continue"
          else
            echo "ℹ GitHub VPN secret update was not required"
          fi

"""
text = text[:start] + new_network_block + text[end:]

replace_once(
    '- name: "24.1 Run price_logger.py on verified VPN1"',
    '- name: "24.1 Run price_logger.py on managed S2 network"',
    "logger step name",
)
replace_once(
    '          PROVIDER_EVENT_FILE: ${{ runner.temp }}/provider-event.json\n          PYTHONUNBUFFERED: "1"',
    '          PROVIDER_EVENT_FILE: ${{ runner.temp }}/provider-event.json\n'
    '          CRYPTO_LOGGER_NETWORK_RECOVERY: "1"\n'
    '          NETWORK_MANAGER_STATE_DIR: ${{ runner.temp }}/network-manager\n'
    '          NETWORK_MANAGER_ALLOWED_ROOTS: ${{ runner.temp }}:${{ github.workspace }}\n'
    '          VPN1_CONFIG: ${{ runner.temp }}/vpn-runtime/vpn1.ovpn\n'
    '          VPN1_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn1-auth.txt\n'
    '          VPN2_CONFIG_FILE: ${{ runner.temp }}/vpn-runtime/vpn2.ovpn\n'
    '          VPN2_AUTH_FILE: ${{ runner.temp }}/vpn-runtime/vpn2-auth.txt\n'
    '          PYTHONUNBUFFERED: "1"',
    "logger S2 environment",
)
replace_once(
    '            (.trading_allowed | type == "boolean") and\n            (.decisions | type == "object" and length == 11)',
    '            (.trading_allowed | type == "boolean") and\n'
    '            (.network_recovery.enabled == true) and\n'
    '            (.network_recovery.switch_count <= 1) and\n'
    '            (.decisions | type == "object" and length == 11)',
    "provider report S2 schema",
)
replace_once(
    '          MANAGER="private_logger/Crypto Logger-Private Repo/network_manager.py"',
    '          MANAGER="private_logger/Crypto Logger-Private Repo/s2_network_manager.py"',
    "disconnect manager",
)
replace_once(
    '            echo "## 🚀 Crypto Logger | Main | Production S1.5"',
    '            echo "## 🚀 Crypto Logger | Main | Production S2"',
    "summary heading",
)
replace_once(
    '''            echo "- **VPN1 qualification:** Passed"
            echo "- **VPN2 qualification:** Passed"
            echo "- **Different public IPs:** Passed"
            echo "- **VPNBook auth recovery:** ${AUTH_RECOVERY}"
            echo "- **GitHub VPN secret update:** ${SECRET_UPDATE}"
            echo "- **Collection network:** VPN1"
            echo "- **Provider-triggered VPN2 switching:** Not enabled yet"''',
    '''            echo "- **Managed startup network:** ${STARTUP_NETWORK:-Unknown}"
            echo "- **VPN2 cold-standby profile:** Validated"
            echo "- **VPNBook auth recovery:** ${AUTH_RECOVERY}"
            echo "- **GitHub VPN secret update:** ${SECRET_UPDATE}"
            echo "- **Provider-triggered network recovery:** Enabled"
            echo "- **Successful reconnects:** $(jq -r '.network_recovery.reconnect_count // 0' "$REPORT")"
            echo "- **Successful VPN2 switches:** $(jq -r '.network_recovery.switch_count // 0' "$REPORT")"
            echo "- **Network after collection:** $(jq -r '.network_recovery.active_network // "unknown"' "$REPORT")"''',
    "network summary",
)

for obsolete in (
    "different_public_ips",
    "Provider-triggered VPN2 switching:** Not enabled yet",
    "SECTION 22 - PROVIDER CONNECTIVITY PROBES",
    "SECTION 21 - ESTABLISH FRESH VPN1 PRODUCTION COLLECTION SESSION",
):
    if obsolete in text:
        raise SystemExit(f"obsolete network workflow text remains: {obsolete}")

for required in (
    'CRYPTO_LOGGER_NETWORK_RECOVERY: "1"',
    "s2_network_manager.py",
    "provider_network_recovery.py",
    "vpn2_standby_validated == true",
    ".network_recovery.switch_count <= 1",
):
    if required not in text:
        raise SystemExit(f"missing required S2 integration marker: {required}")

path.write_text(text, encoding="utf-8")
print("S2 crypto_runner patch prepared successfully")
