#!/system/bin/sh
# Copies the video recordings from CarPlay's (DiPO's) private files to every USB stick that has a
# CarPlayUltraLite-Video folder (hmgapid usb lists only those): the phone's settings and overlay streams
# (files/cpc-video-side/<session>/, see VideoSideChannel) into side/<session>/, and the video engine's trace into
# trace/. Checks every 30 s; a file is copied again only when it changed. Reads CarPlay's files, writes
# only to the stick. Head unit shell: mksh and toolbox (no find, sed, basename).
SRC=${CPC_VIDEO_FILES:-/data/data/com.daudio.app.dipo/files}   # (the variable: the off-car test only)
SIDE=$SRC/cpc-video-side

sum() {   # a file's MD5 (toolbox md5: "<hash>  <file>"), or nothing
    set -- $(md5 "$1" 2>/dev/null)
    echo "$1"
}

put() {   # put <file> <folder on the stick>: copied when missing there; a .txt (still growing) also when it changed
    [ -f "$1" ] || return 0
    to="$2/${1##*/}"
    if [ -f "$to" ]; then
        case "$1" in *.txt) ;; *) return 0 ;; esac
        [ "$(sum "$1")" = "$(sum "$to")" ] && return 0
    fi
    cp "$1" "$to" 2>/dev/null && echo "copied ${1#$SRC/} to $2"
}

echo "video recordings to USB: waiting for a stick with a CarPlayUltraLite-Video folder"
while true; do
    for d in $(hmgapid usb); do
        [ -d "$d/trace" ] || mkdir "$d/trace" 2>/dev/null
        put "$SRC/cpc-video-trace.txt" "$d/trace"
        put "$SRC/cpc-video-trace.1.txt" "$d/trace"
        [ -d "$SIDE" ] || continue
        [ -d "$d/side" ] || mkdir "$d/side" 2>/dev/null
        for s in $(ls "$SIDE"); do
            [ -d "$SIDE/$s" ] || continue
            [ -d "$d/side/$s" ] || mkdir "$d/side/$s" 2>/dev/null
            for f in $(ls "$SIDE/$s"); do
                put "$SIDE/$s/$f" "$d/side/$s"
            done
        done
    done
    sleep 30
done
