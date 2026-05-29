#!/bin/sh
# Migrate-before-serve (spec §6): every container start brings the mounted
# /data DB to head, so `docker compose pull` of a newer image upgrades an
# existing install. Then hand off to the web app. Args after the script
# (e.g. --no-mdns) are forwarded to `serve`.
set -e

curbcam db upgrade --data-dir /data

exec curbcam serve \
    --host 0.0.0.0 \
    --port 8080 \
    --data-dir /data \
    --media-dir /media \
    --config /data/curbcam.yaml \
    "$@"
