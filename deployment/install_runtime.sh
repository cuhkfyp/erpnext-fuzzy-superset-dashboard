#!/usr/bin/env bash
set -euo pipefail

readonly repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly superset_home="/home/frappe-user/superset"
readonly config_path="${superset_home}/superset_config.py"
readonly marker_begin="# BEGIN MANAGED CCD DASHBOARD RUNTIME"
readonly marker_end="# END MANAGED CCD DASHBOARD RUNTIME"
config_tmp=""

cleanup() {
    if [[ -n "${config_tmp}" ]]; then
        rm -f "${config_tmp}"
    fi
}
trap cleanup EXIT

test "$(id -u)" -eq 0
test -s "${config_path}"
test -s "${superset_home}/superset.key"

backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/root/erpnext_docker_volume/private_security/superset-config-backups/${backup_stamp}"
install -d -m 0700 "${backup_dir}"
install -m 0600 "${config_path}" "${backup_dir}/superset_config.py.before"

config_tmp="$(mktemp "${superset_home}/superset_config.py.XXXXXX")"
awk -v begin="${marker_begin}" -v end="${marker_end}" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
    END { if (skip) exit 42 }
' "${config_path}" >"${config_tmp}"
{
    printf '\n%s\n' "${marker_begin}"
    cat "${repo_root}/deployment/superset_runtime_config.py"
    printf '%s\n' "${marker_end}"
} >>"${config_tmp}"
config_uid="$(stat -c '%u' "${config_path}")"
config_gid="$(stat -c '%g' "${config_path}")"
config_mode="$(stat -c '%a' "${config_path}")"
install -o "${config_uid}" -g "${config_gid}" -m "${config_mode}" \
    "${config_tmp}" "${config_path}"

umask 077
printf 'SUPERSET_SECRET_KEY=%s\n' "$(tr -d '\r\n' <"${superset_home}/superset.key")" \
    >"${superset_home}/hksr-superset.env"
chown frappe-user:frappe-user "${superset_home}/hksr-superset.env"
chmod 0600 "${superset_home}/hksr-superset.env"

install -m 0644 "${repo_root}/deployment/hksr-superset.service" /etc/systemd/system/hksr-superset.service
install -m 0644 "${repo_root}/deployment/hksr-mariadb-proxy.socket" /etc/systemd/system/hksr-mariadb-proxy.socket
install -m 0644 "${repo_root}/deployment/hksr-mariadb-proxy.service" /etc/systemd/system/hksr-mariadb-proxy.service
install -m 0755 "${repo_root}/deployment/hksr-superset-restart.sh" /usr/local/sbin/hksr-superset-restart
systemctl daemon-reload
systemctl enable --now hksr-mariadb-proxy.socket
systemctl enable hksr-superset.service
/usr/local/sbin/hksr-superset-restart
