#!/usr/bin/env bash

set -euo pipefail

SRC_RPM=""
PATCH_DIR=""
PLATFORM="native"
CC_BIN="${CC:-}"
CFLAGS_VALUE="${CFLAGS:--g -O2}"
JOBS="$(nproc 2>/dev/null || echo 1)"
OUTPUT=""
WORK_DIR=""

usage() {
  cat <<'EOF'
Usage: build.sh [options]

Options:
  --src-rpm     dnsmasq source rpm
  --patch-dir   extra patches directory with series
  --platform    native/x86_64/aarch64/loongarch64/mips64el
  --cc          compiler path/name
  --cflags      compiler flags
  --jobs        make jobs
  --output      copy built binary to path
  --work-dir    build work directory
  -h, --help    show this help
EOF
}

log() {
  printf '[dnsmasq-build] %s\n' "$*"
}

die() {
  printf '[dnsmasq-build] ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --src-rpm)
        SRC_RPM="$2"
        shift 2
        ;;
      --patch-dir|--patches-dir)
        PATCH_DIR="$2"
        shift 2
        ;;
      --platform|--target-platform)
        PLATFORM="$2"
        shift 2
        ;;
      --cc)
        CC_BIN="$2"
        shift 2
        ;;
      --cflags)
        CFLAGS_VALUE="$2"
        shift 2
        ;;
      --jobs|-j)
        JOBS="$2"
        shift 2
        ;;
      --output)
        OUTPUT="$2"
        shift 2
        ;;
      --work-dir)
        WORK_DIR="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
  done
}

abs_path() {
  local path="$1"
  if [ -d "$path" ]; then
    (cd "$path" && pwd)
  else
    local dir
    local base
    dir="$(dirname "$path")"
    base="$(basename "$path")"
    (cd "$dir" && printf '%s/%s\n' "$(pwd)" "$base")
  fi
}

default_cc_for_platform() {
  local platform="$1"
  local host_arch
  host_arch="$(uname -m)"

  case "$platform" in
    native)
      printf '%s\n' "${CC_BIN:-cc}"
      ;;
    x86_64|amd64)
      if [ "$host_arch" = "x86_64" ]; then
        printf '%s\n' "${CC_BIN:-cc}"
      else
        printf '%s\n' "${CC_BIN:-x86_64-linux-gnu-gcc}"
      fi
      ;;
    aarch64|arm64)
      printf '%s\n' "${CC_BIN:-aarch64-linux-gnu-gcc}"
      ;;
    loongarch64)
      printf '%s\n' "${CC_BIN:-loongarch64-linux-gnu-gcc}"
      ;;
    mips64el)
      printf '%s\n' "${CC_BIN:-mips64el-linux-gnuabi64-gcc}"
      ;;
    *)
      printf '%s\n' "${CC_BIN:-${platform}-linux-gnu-gcc}"
      ;;
  esac
}

prepare_work_dir() {
  if [ -n "$WORK_DIR" ]; then
    mkdir -p "$WORK_DIR"
    WORK_DIR="$(abs_path "$WORK_DIR")"
    rm -rf "${WORK_DIR:?}/srpm" "${WORK_DIR:?}/src"
  else
    WORK_DIR="$(mktemp -d /tmp/dnsmasq-build.XXXXXX)"
  fi
  mkdir -p "${WORK_DIR}/srpm" "${WORK_DIR}/src"
}

cleanup_work_dir() {
  if [ -n "$WORK_DIR" ]; then
    rm -f "${WORK_DIR}/patch-check.log"
    rm -rf "$WORK_DIR"
  fi
}

extract_srpm() {
  log "extract source rpm: ${SRC_RPM}"
  (cd "${WORK_DIR}/srpm" && rpm2cpio "$SRC_RPM" | cpio -idmu >/dev/null 2>&1)
}

spec_file() {
  local spec
  spec="$(find "${WORK_DIR}/srpm" -maxdepth 1 -type f -name '*.spec' | sort | head -n1)"
  [ -n "$spec" ] || die "missing spec file in source rpm"
  printf '%s\n' "$spec"
}

spec_value() {
  local spec="$1"
  local key="$2"
  sed -n "s/^${key}:[[:space:]]*//p" "$spec" | head -n1 | awk '{print $1}'
}

expand_spec_name() {
  local value="$1"
  local name="$2"
  local version="$3"

  value="${value//\%\{name\}/$name}"
  value="${value//\%\{version\}/$version}"
  value="${value//\%\{\?extraversion\}/}"
  value="${value//\%\{?extraversion\}/}"
  basename "$value"
}

source_archive() {
  local spec="$1"
  local name="$2"
  local version="$3"
  local source
  local candidate
  local found

  found="$(find "${WORK_DIR}/srpm" -maxdepth 1 -type f \
    \( -name "${name}-${version}.tar.*" -o -name "${name}-${version}.tgz" \) |
    sort |
    head -n1)"
  if [ -n "$found" ]; then
    basename "$found"
    return 0
  fi

  source="$(spec_value "$spec" "Source0")"
  [ -n "$source" ] || die "missing Source0 in spec"
  candidate="$(expand_spec_name "$source" "$name" "$version")"
  [ -f "${WORK_DIR}/srpm/${candidate}" ] || die "missing source archive: ${candidate}"
  printf '%s\n' "$candidate"
}

spec_patch_files() {
  local spec="$1"
  local name="$2"
  local version="$3"

  sed -n 's/^Patch[0-9]*:[[:space:]]*//p' "$spec" |
    awk '{print $1}' |
    while IFS= read -r patch_name; do
      [ -z "$patch_name" ] && continue
      expand_spec_name "$patch_name" "$name" "$version"
    done
}

trim_series_line() {
  local line="$1"
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s\n' "$line"
}

extract_source() {
  local archive="$1"
  [ -f "${WORK_DIR}/srpm/${archive}" ] || die "missing source archive: ${archive}"
  log "extract source archive: ${archive}"
  tar -xf "${WORK_DIR}/srpm/${archive}" -C "${WORK_DIR}/src" --strip-components=1
  [ -f "${WORK_DIR}/src/Makefile" ] || die "source archive is not dnsmasq root"
}

apply_one_patch() {
  local patch_file="$1"
  local patch_name
  patch_name="$(basename "$patch_file")"

  if patch --dry-run --no-backup-if-mismatch -p1 < "$patch_file" >"${WORK_DIR}/patch-check.log" 2>&1; then
    log "apply patch: ${patch_name}"
    patch --no-backup-if-mismatch -p1 < "$patch_file" >/dev/null
    return 0
  fi

  if patch --dry-run --no-backup-if-mismatch -R -p1 < "$patch_file" >/dev/null 2>&1; then
    log "skip already applied patch: ${patch_name}"
    return 0
  fi

  cat "${WORK_DIR}/patch-check.log" >&2
  die "failed to apply patch: ${patch_name}"
}

apply_spec_patches() {
  local spec="$1"
  local name="$2"
  local version="$3"
  local patch_name
  local patch_path

  while IFS= read -r patch_name; do
    [ -z "$patch_name" ] && continue
    patch_path="${WORK_DIR}/srpm/${patch_name}"
    [ -f "$patch_path" ] || die "missing source rpm patch file: ${patch_name}"
    apply_one_patch "$patch_path"
  done < <(spec_patch_files "$spec" "$name" "$version")
}

apply_extra_series() {
  local series_file="${PATCH_DIR}/series"
  local line
  local patch_name

  [ -f "$series_file" ] || die "missing series file: ${series_file}"

  while IFS= read -r line || [ -n "$line" ]; do
    patch_name="$(trim_series_line "$line")"
    [ -z "$patch_name" ] && continue

    [ -f "${PATCH_DIR}/${patch_name}" ] || die "missing patch file: ${PATCH_DIR}/${patch_name}"
    apply_one_patch "${PATCH_DIR}/${patch_name}"
  done < "$series_file"
}

build_dnsmasq() {
  local cc="$1"

  need_cmd "$cc"
  log "build dnsmasq with CC=${cc}, CFLAGS=${CFLAGS_VALUE}, jobs=${JOBS}"
  make clean
  make -j"${JOBS}" CC="$cc" CFLAGS="${CFLAGS_VALUE}"
}

copy_output() {
  local src_bin="${WORK_DIR}/src/src/dnsmasq"
  [ -x "$src_bin" ] || die "missing built binary: ${src_bin}"

  if [ -n "$OUTPUT" ]; then
    mkdir -p "$(dirname "$OUTPUT")"
    cp "$src_bin" "$OUTPUT"
    chmod 0755 "$OUTPUT"
    log "copied binary to ${OUTPUT}"
  fi
}

main() {
  parse_args "$@"

  need_cmd rpm2cpio
  need_cmd cpio
  need_cmd patch
  need_cmd sed
  need_cmd awk
  need_cmd tar

  [ -n "$SRC_RPM" ] || die "--src-rpm is required"
  [ -n "$PATCH_DIR" ] || die "--patch-dir is required"
  SRC_RPM="$(abs_path "$SRC_RPM")"
  PATCH_DIR="$(abs_path "$PATCH_DIR")"
  [ -f "$SRC_RPM" ] || die "source rpm does not exist: ${SRC_RPM}"
  [ -d "$PATCH_DIR" ] || die "patch directory does not exist: ${PATCH_DIR}"

  local cc
  cc="$(default_cc_for_platform "$PLATFORM")"

  prepare_work_dir
  trap cleanup_work_dir EXIT

  extract_srpm

  local spec
  local name
  local version
  local archive
  spec="$(spec_file)"
  name="$(spec_value "$spec" "Name")"
  version="$(spec_value "$spec" "Version")"
  [ -n "$name" ] || die "missing Name in spec"
  [ -n "$version" ] || die "missing Version in spec"
  archive="$(source_archive "$spec" "$name" "$version")"

  log "source rpm: ${SRC_RPM}"
  log "package: ${name}-${version}"
  log "extra patch directory: ${PATCH_DIR}"
  log "work directory: ${WORK_DIR}"
  log "target platform: ${PLATFORM}"

  extract_source "$archive"
  cd "${WORK_DIR}/src"
  apply_spec_patches "$spec" "$name" "$version"
  apply_extra_series
  build_dnsmasq "$cc"
  copy_output

  if [ "$PLATFORM" = "native" ] || [ "$PLATFORM" = "$(uname -m)" ]; then
    "${WORK_DIR}/src/src/dnsmasq" --version | sed -n '1,5p'
  fi
}

main "$@"
