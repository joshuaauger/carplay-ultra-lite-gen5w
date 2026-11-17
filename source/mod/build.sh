#!/bin/sh
# cp-climate's package step, run by the HMG-API mod SDK's bin/mkmodpkg.sh from the repo root, after
# bin/build-mod.sh built the mod's classes (or by HMG-API's own tools/mkmodpkg.sh from mods/cp-climate):
#   sh source/mod/build.sh <package folder>
# Merges the video engine (tools/video: ExoPlayer through the phone's proxy, BouncyCastle TLS 1.3) into
# hooks.jar: cp-climate's classes + the engine + its libraries, shrunk by R8 to one dex for Android 4.4.
# Without tools/video the package keeps HMG-API's plain hooks.jar (no engine: answers only).
set -e
PKG=${1:?usage: build.sh <package folder>}
HERE=$(cd "$(dirname "$0")" && pwd)
V=$HERE/tools/video
[ -d "$V/src" ] || exit 0
# CI and fresh checkouts have no libraries: fetch them (SHA-256 checked by fetch-libs.sh)
{ [ -f "$V/r8.jar" ] && [ -d "$V/libs" ]; } || sh "$V/fetch-libs.sh" >&2
ID=$(basename "$HERE")
# the compiled mod classes: HMGAPI_MOD_WORK/classes if set, else out/mod-classes/<id> (HMG-API's own build),
# out/work/<id>/classes (the SDK's mod workflow) or the temp work dir mkmodpkg.sh uses when nothing was built first
CORE=""
for c in "${HMGAPI_MOD_WORK:+$HMGAPI_MOD_WORK/classes}" "$PWD/out/mod-classes/$ID" "$PWD/out/work/$ID/classes" "$(dirname "$PKG")/work/classes"; do
    if [ -n "$c" ] && [ -d "$c" ]; then CORE=$c; break; fi
done
[ -n "$CORE" ] || { echo "build.sh: no compiled mod classes (run the SDK's bin/build-mod.sh first)" >&2; exit 1; }
SDK=${ANDROID_HOME:-$HOME/Library/Android/sdk}
ANDROID_JAR=$(ls -d "$SDK"/platforms/android-34/android.jar 2>/dev/null || ls -d "$SDK"/platforms/android-*/android.jar | sort -V | tail -1)
LIBS=$(ls "$V"/libs/*.jar | tr '\n' ':')
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
mkdir -p "$W/classes"
javac --release 8 -Xlint:-options -nowarn -cp "$ANDROID_JAR:$CORE:$LIBS" -d "$W/classes" $(find "$V/src" -name '*.java')
cp -R "$CORE"/. "$W/classes/"
(cd "$W/classes" && jar cf "$W/program.jar" .)
RULES=""
for r in "$V"/rules/*.pro; do RULES="$RULES --pg-conf $r"; done
# program: cp-climate + engine + libraries (androidx.annotation is compile-only)
PROGRAM="$W/program.jar"
for j in "$V"/libs/*.jar; do case "$(basename "$j")" in annotation-*) ;; *) PROGRAM="$PROGRAM $j" ;; esac; done
java -cp "$V/r8.jar" com.android.tools.r8.R8 --release --min-api 19 --lib "$ANDROID_JAR" --classpath "$V/libs/annotation-1.3.0.jar" \
    $RULES --output "$W/out.zip" $PROGRAM >"$W/r8.log" 2>&1 || { cat "$W/r8.log" >&2; exit 1; }
DEXES=$(unzip -l "$W/out.zip" | grep -c 'classes[0-9]*\.dex' || true)
[ "$DEXES" = 1 ] || { echo "build.sh: R8 made $DEXES dex files; Android 4.4's class loader reads only one" >&2; exit 1; }
mkdir -p "$W/jar" && (cd "$W/jar" && unzip -q "$W/out.zip" classes.dex)
rm -f "$PKG/hooks.jar"
(cd "$W/jar" && TZ=UTC touch -d 2026-01-01T00:00:00 classes.dex && zip -q -X "$PKG/hooks.jar" classes.dex)
echo "build.sh: hooks.jar with the video engine, $(wc -c < "$W/jar/classes.dex" | tr -d ' ') bytes of dex" >&2
