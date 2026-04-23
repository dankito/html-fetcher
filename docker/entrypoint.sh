#!/bin/sh
# entrypoint.sh

# Runs as root, then drops privileges to appuser via gosu.

# Optionally set UID and/or GID in your docker-compose.yml environment
# to dynamically remap appuser's UID/GID, so that files written to mounted
# volumes are owned by your host user and remain easily accessible.

is_integer() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

if [ -n "$UID" ] || [ -n "$GID" ]; then

    if [ -n "$UID" ] && ! is_integer "$UID"; then
        echo "[entrypoint] ERROR: UID='${UID}' is not a valid integer. Not changing UID of appuser." >&2
    else
      OLD_UID="$(id -u appuser)"

      if [ -n "$UID" ] && [ "$UID" != "$OLD_UID" ]; then
          usermod -u "$UID" appuser
          echo "[entrypoint] Changed UID of appuser: ${OLD_UID} -> ${UID}."
          find /app  -user "$OLD_UID" -exec chown -h appuser {} \;
          find /data -user "$OLD_UID" -exec chown -h appuser {} \;
      fi
    fi

    if [ -n "$GID" ] && ! is_integer "$GID"; then
        echo "[entrypoint] ERROR: GID='${GID}' is not a valid integer. Not changing GID of group appuser.." >&2
    else
      OLD_GID="$(id -g appuser)"

      if [ -n "$GID" ] && [ "$GID" != "$OLD_GID" ]; then
          groupmod -g "$GID" appuser
          echo "[entrypoint] Changed GID of group appuser: ${OLD_GID} -> ${GID}."
          find /app  -group "$OLD_GID" -exec chgrp -h appuser {} \;
          find /data -group "$OLD_GID" -exec chgrp -h appuser {} \;
      fi
    fi

fi


# drop to appuser
exec gosu appuser "$@"