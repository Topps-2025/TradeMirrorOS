#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
  set -- --help
fi

case "$1" in
  cli)
    shift
    exec python /app/finance-journal-orchestrator/scripts/finance_journal_cli.py "$@"
    ;;
  gateway)
    shift
    exec python /app/finance-journal-orchestrator/scripts/finance_journal_gateway.py "$@"
    ;;
  session-agent)
    shift
    exec python /app/finance-journal-orchestrator/scripts/finance_journal_session_agent.py "$@"
    ;;
  *)
    exec python /app/finance-journal-orchestrator/scripts/finance_journal_cli.py "$@"
    ;;
esac
