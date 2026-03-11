#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SRC_DIR="$ROOT_DIR/runtime/keycloak/provider-src"
OUT_DIR="$ROOT_DIR/runtime/keycloak/providers"
OUT_JAR="$OUT_DIR/mediamtx-script-provider.jar"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mediamtx-script-provider.XXXXXX")

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

mkdir -p "$OUT_DIR"
cp -R "$SRC_DIR"/. "$TMP_DIR"/

(
    cd "$TMP_DIR"
    jar --create --file "$OUT_JAR" .
)

printf 'Built %s\n' "$OUT_JAR"
