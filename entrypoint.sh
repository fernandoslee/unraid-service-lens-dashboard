#!/bin/sh
# Detect Docker socket GID and grant access to appuser
SOCK=/var/run/docker.sock
if [ -S "$SOCK" ]; then
    SOCK_GID=$(stat -c '%g' "$SOCK" 2>/dev/null || stat -f '%g' "$SOCK" 2>/dev/null)
    if [ -n "$SOCK_GID" ] && [ "$SOCK_GID" != "0" ]; then
        # Create a group with the socket's GID and add appuser
        getent group "$SOCK_GID" >/dev/null 2>&1 || addgroup --gid "$SOCK_GID" docker-host
        adduser appuser "$(getent group "$SOCK_GID" | cut -d: -f1)" 2>/dev/null
    elif [ "$SOCK_GID" = "0" ]; then
        # Socket owned by root — add appuser to root group
        adduser appuser root 2>/dev/null
    fi
fi

exec gosu appuser "$@"
