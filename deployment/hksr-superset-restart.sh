#!/usr/bin/env bash
set -euo pipefail

readonly service_name="hksr-superset.service"
readonly superset_home="/home/frappe-user/superset"
readonly python_bin="/home/frappe-user/venv/bin/python"
readonly health_url="https://127.0.0.1:8088/health"
readonly legacy_log="${superset_home}/superset_run.log"

legacy_pid=""
started_service=0

preflight() {
    test -x "${python_bin}"
    test -x /home/frappe-user/venv/bin/gunicorn
    test -s "${superset_home}/superset_config.py"
    test -s "${superset_home}/cert/hksr.org.hk.pem"
    test -s "${superset_home}/cert/hksr.org.hk.key"
    runuser -u frappe-user -- env \
        SUPERSET_CONFIG_PATH="${superset_home}/superset_config.py" \
        FLASK_APP=superset \
        "${python_bin}" -c 'from superset.app import create_app; app=create_app(); assert app'
}

find_legacy_pid() {
    local frappe_uid
    frappe_uid="$(id -u frappe-user)"
    ps -eo pid=,uid=,args= | awk -v frappe_uid="${frappe_uid}" '
        $2 == frappe_uid &&
        $0 ~ /\/home\/frappe-user\/venv\/bin\/superset run -h 0\.0\.0\.0 -p 8088/ {
            print $1
        }' | head -n 1
}

wait_for_exit() {
    local pid="$1"
    local attempt
    for attempt in $(seq 1 30); do
        if ! kill -0 "${pid}" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

health_check() {
    local attempt
    for attempt in $(seq 1 45); do
        if curl --silent --show-error --fail --insecure --max-time 5 "${health_url}" >/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

restore_legacy() {
    systemctl stop "${service_name}" 2>/dev/null || true
    runuser -u frappe-user -- sh -c \
        "cd '${superset_home}' && nohup /home/frappe-user/venv/bin/superset run -h 0.0.0.0 -p 8088 --with-threads --debugger --cert '${superset_home}/cert/hksr.org.hk.pem' --key '${superset_home}/cert/hksr.org.hk.key' >>'${legacy_log}' 2>&1 &"
    health_check
}

rollback() {
    local rc="$?"
    if [[ "${started_service}" == 1 && -n "${legacy_pid}" ]]; then
        printf '%s\n' "Managed start failed; restoring the prior exact Superset command." >&2
        restore_legacy || true
    fi
    exit "${rc}"
}
trap rollback ERR

preflight
legacy_pid="$(find_legacy_pid)"

if systemctl is-active --quiet "${service_name}"; then
    systemctl stop "${service_name}"
fi

if [[ -n "${legacy_pid}" ]] && kill -0 "${legacy_pid}" 2>/dev/null; then
    kill -TERM "${legacy_pid}"
    if ! wait_for_exit "${legacy_pid}"; then
        kill -KILL "${legacy_pid}"
        wait_for_exit "${legacy_pid}"
    fi
fi

started_service=1
systemctl start "${service_name}"
health_check
systemctl is-active --quiet "${service_name}"
trap - ERR
printf '%s\n' "${service_name} is healthy at ${health_url}"
