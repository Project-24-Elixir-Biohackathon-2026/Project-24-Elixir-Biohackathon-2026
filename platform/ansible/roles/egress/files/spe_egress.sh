#!/bin/sh
# Sandbox egress filter (spe_harden_egress, ladder level L3): the sandbox reaches only the
# API host on 443. FORWARD traffic is filtered in chain SPE-EGRESS (jumped to from DOCKER-USER),
# traffic to the host itself in SPE-EGRESS-IN (from INPUT). Usage: spe_egress.sh apply|remove|status
set -eu
IPT=${IPTABLES:-iptables}
ENV_FILE=${SPE_EGRESS_ENV:-/etc/spe/egress.env}

apply() {
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  : "${SANDBOX_IP:?}" "${API_IP:?}" "${API_PORT:?}"
  $IPT -N SPE-EGRESS 2>/dev/null || true
  $IPT -F SPE-EGRESS
  $IPT -A SPE-EGRESS -s "$SANDBOX_IP/32" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  $IPT -A SPE-EGRESS -s "$SANDBOX_IP/32" -p tcp -m conntrack --ctorigdst "$API_IP" --ctorigdstport "$API_PORT" -j RETURN
  $IPT -A SPE-EGRESS -s "$SANDBOX_IP/32" -j DROP
  $IPT -C DOCKER-USER -j SPE-EGRESS 2>/dev/null || $IPT -I DOCKER-USER 1 -j SPE-EGRESS
  $IPT -N SPE-EGRESS-IN 2>/dev/null || true
  $IPT -F SPE-EGRESS-IN
  $IPT -A SPE-EGRESS-IN -s "$SANDBOX_IP/32" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  $IPT -A SPE-EGRESS-IN -s "$SANDBOX_IP/32" -d "$API_IP/32" -p tcp --dport "$API_PORT" -j RETURN
  $IPT -A SPE-EGRESS-IN -s "$SANDBOX_IP/32" -j DROP
  $IPT -C INPUT -j SPE-EGRESS-IN 2>/dev/null || $IPT -I INPUT 1 -j SPE-EGRESS-IN
}

remove() {
  while $IPT -D DOCKER-USER -j SPE-EGRESS 2>/dev/null; do :; done
  while $IPT -D INPUT -j SPE-EGRESS-IN 2>/dev/null; do :; done
  for c in SPE-EGRESS SPE-EGRESS-IN; do
    $IPT -F "$c" 2>/dev/null || true
    $IPT -X "$c" 2>/dev/null || true
  done
}

case "${1:-}" in
  apply) apply ;;
  remove) remove ;;
  # The chains alone are not enough: without its jump a chain filters nothing.
  status) $IPT -S SPE-EGRESS && $IPT -S SPE-EGRESS-IN
          $IPT -C DOCKER-USER -j SPE-EGRESS && $IPT -C INPUT -j SPE-EGRESS-IN ;;
  *) echo "usage: $0 apply|remove|status" >&2; exit 2 ;;
esac
