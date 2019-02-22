#!/bin/bash
# Entrypoint for application.
set -e

# If the user started things with an option e.g. "-d" then run our program, otherwise
# assume we should be running an arbitrary application
if [ "${1:0:1}" = '-' ]; then
    set -- python hangupsbot.py "$@"
fi
exec "$@"
