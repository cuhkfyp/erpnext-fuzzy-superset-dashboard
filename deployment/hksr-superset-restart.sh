#!/usr/bin/env bash
set -euo pipefail

readonly service_name="hksr-superset.service"
readonly superset_home="/home/frappe-user/superset"
readonly python_bin="/home/frappe-user/venv/bin/python"
readonly health_url="https://127.0.0.1:8088/health"
readonly legacy_log="${superset_home}/superset_run.log"
readonly certificate_file="${superset_home}/certs/fullchain.pem"
readonly certificate_key="${superset_home}/certs/hksr.org.hk.key"

legacy_pid=""
unmanaged_gunicorn_pid=""
started_service=0

preflight() {
    test -x "${python_bin}"
    test -x /home/frappe-user/venv/bin/gunicorn
    test -s "${superset_home}/superset_config.py"
    test -s "${certificate_file}"
    test -s "${certificate_key}"
    openssl x509 -in "${certificate_file}" -noout -checkend 86400
    runuser -u frappe-user -- env \
        SUPERSET_CONFIG_PATH="${superset_home}/superset_config.py" \
        FLASK_APP=superset \
        "${python_bin}" -c 'from superset.app import create_app; app=create_app(); assert app'
}

find_unmanaged_gunicorn_pid() {
    local frappe_uid
    frappe_uid="$(id -u frappe-user)"
    ps -eo pid=,ppid=,uid=,args= | awk -v frappe_uid="${frappe_uid}" '
        $2 == 1 &&
        $3 == frappe_uid &&
        $0 ~ /\/home\/frappe-user\/venv\/bin\/gunicorn -w 10 -k gevent/ &&
        $0 ~ / -b 0\.0\.0\.0:8088 / &&
        $0 ~ / --daemon / &&
        $0 ~ /superset\.app:create_app\(\)/ {
            print $1
        }' | head -n 1
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
        "cd '${superset_home}' && nohup /home/frappe-user/venv/bin/superset run -h 0.0.0.0 -p 8088 --with-threads --debugger --cert '${certificate_file}' --key '${certificate_key}' >>'${legacy_log}' 2>&1 &"
    health_check
}

restore_unmanaged_gunicorn() {
    systemctl stop "${service_name}" 2>/dev/null || true
    runuser -u frappe-user -- env HOME=/home/frappe-user \
        "${superset_home}/run.sh"
    health_check
}

stop_exact_pid() {
    local pid="$1"
    kill -TERM "${pid}"
    if ! wait_for_exit "${pid}"; then
        kill -KILL "${pid}"
        wait_for_exit "${pid}"
    fi
}

rollback() {
    local rc="$?"
    if [[ "${started_service}" == 1 ]]; then
        if [[ -n "${unmanaged_gunicorn_pid}" ]]; then
            printf '%s\n' "Managed start failed; restoring the prior unmanaged Gunicorn command." >&2
            restore_unmanaged_gunicorn || true
        elif [[ -n "${legacy_pid}" ]]; then
            printf '%s\n' "Managed start failed; restoring the prior exact Superset command." >&2
            restore_legacy || true
        fi
    fi
    exit "${rc}"
}
trap rollback ERR

preflight
legacy_pid="$(find_legacy_pid)"
unmanaged_gunicorn_pid="$(find_unmanaged_gunicorn_pid)"

if [[ -n "${legacy_pid}" && -n "${unmanaged_gunicorn_pid}" ]]; then
    printf '%s\n' "Refusing cutover because two unmanaged Superset runtimes were detected." >&2
    exit 1
fi
if [[ -n "${unmanaged_gunicorn_pid}" ]]; then
    test -x "${superset_home}/run.sh"
fi

if systemctl is-active --quiet "${service_name}"; then
    systemctl stop "${service_name}"
fi

if [[ -n "${legacy_pid}" ]] && kill -0 "${legacy_pid}" 2>/dev/null; then
    stop_exact_pid "${legacy_pid}"
fi

if [[ -n "${unmanaged_gunicorn_pid}" ]] && kill -0 "${unmanaged_gunicorn_pid}" 2>/dev/null; then
    stop_exact_pid "${unmanaged_gunicorn_pid}"
fi

started_service=1
systemctl start "${service_name}"
health_check
systemctl is-active --quiet "${service_name}"
trap - ERR
printf '%s\n' "${service_name} is healthy at ${health_url}"
