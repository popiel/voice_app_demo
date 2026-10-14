#!/usr/bin/env bash
#
# Bootstrap a Windows 11 machine for voice_app_demo development.
#
# PREREQUISITES (do these by hand first):
#   1. Install Git for Windows (provides git AND this Git Bash shell).
#   2. git clone <repo-url> and cd into it, then run: ./scripts/bootstrap_windows.sh
#
# Everything below is per-user (no admin rights needed) and CPU-only.
# Long steps (Ollama model pull, sample build, full verify) can be skipped
# and re-run later; re-running this script is safe (idempotent checks first).
#
# Usage: ./scripts/bootstrap_windows.sh [--skip-python] [--skip-ollama]
#          [--skip-models] [--skip-samples] [--verify-full] [--help]
#
set -euo pipefail

SKIP_PYTHON=0
SKIP_OLLAMA=0
SKIP_MODELS=0
SKIP_SAMPLES=0
VERIFY_FULL=0

usage() {
  cat <<'EOF'
Usage: ./scripts/bootstrap_windows.sh [flags]
  Bootstraps a Windows 11 machine for voice_app_demo development.
  Run from the repo root in Git Bash after cloning. Idempotent; safe to re-run.
Flags:
  --skip-python   skip the Python 3.14 install/upgrade attempt
  --skip-ollama   skip Ollama install, serve, and llama3.2 pull
  --skip-models   skip Hugging Face model warmup downloads
  --skip-samples  skip rebuilding test/samples/*.wav fixtures
  --verify-full   also run the full sample_03 pipeline (~20 min CPU)
  --help          print this help
EOF
}

for arg in "$@"; do
  case "$arg" in
    --skip-python) SKIP_PYTHON=1 ;;
    --skip-ollama) SKIP_OLLAMA=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --skip-samples) SKIP_SAMPLES=1 ;;
    --verify-full) VERIFY_FULL=1 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; usage >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Python 3.14 (torch/av pins below are verified on cp314 only).
# ---------------------------------------------------------------------------
PYBIN=""
if [ "$SKIP_PYTHON" -eq 0 ]; then
  log "Step 1: Python 3.14"
  if command -v python3 >/dev/null 2>&1 && python3 --version 2>&1 | grep -q "3\.14"; then
    PYBIN="python3"
  else
    # Well-known per-user install locations before falling back to winget.
    for cand in "$LOCALAPPDATA/Programs/Python/Python314/python.exe" \
                "/c/Python314/python.exe"; do
      if [ -x "$cand" ]; then PYBIN="$cand"; break; fi
    done
    if [ -z "$PYBIN" ]; then
      if command -v winget >/dev/null 2>&1; then
        log "Installing Python 3.14 via winget (user scope, no admin)"
        winget install -e --id Python.Python.3.14 --scope user \
          --accept-package-agreements --accept-source-agreements --silent \
          || fail "winget Python install failed; install python.org 3.14.x by hand (per-user, add to PATH)"
        hash -r
        for cand in "$LOCALAPPDATA/Programs/Python/Python314/python.exe" \
                    "/c/Python314/python.exe"; do
          if [ -x "$cand" ]; then PYBIN="$cand"; break; fi
        done
        [ -z "$PYBIN" ] && PYBIN="python3"
      else
        fail "No Python 3.14 found and no winget available; install python.org 3.14.x by hand"
      fi
    fi
  fi
else
  PYBIN="python3"
fi
"$PYBIN" --version
"$PYBIN" -c "import sys; print(sys.executable)"
case "$("$PYBIN" --version 2>&1)" in
  *"3.14."*) ;;
  *) fail "Need Python 3.14.x (av==15.1.0 has no wheels for other versions)" ;;
esac

# ---------------------------------------------------------------------------
# Step 2: session + persistent environment.
# ---------------------------------------------------------------------------
log "Step 2: environment variables"
export PYTHONUTF8=1
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
# Persist for future shells (best-effort; harmless if setx is unavailable).
setx PYTHONUTF8 1 >/dev/null 2>&1 || warn "could not persist PYTHONUTF8 (set it manually)"
setx HF_HUB_DISABLE_SYMLINKS_WARNING 1 >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Step 3: pip packages, pinned and ordered (order matters).
# ---------------------------------------------------------------------------
log "Step 3: pip packages"
"$PYBIN" -m pip install -U pip
# 3a. DSP core first (fast; static ffmpeg binary, no system ffmpeg needed).
"$PYBIN" -m pip install \
  "numpy==2.5.4" "soundfile==0.14.0" "imageio-ffmpeg==0.6.0" "pytest==9.1.1"
# 3b. torch CPU pair: custom index AND matched pins (index torchaudio lags
# torch; a 2.14/2.11 mix breaks Demucs). Never use default PyPI torch here
# (multi-GB CUDA build).
"$PYBIN" -m pip install "torch==2.11.0" "torchaudio==2.11.0" \
  --index-url https://download.pytorch.org/whl/cpu
# 3c. ML stages.
"$PYBIN" -m pip install \
  "demucs==4.1.0" "silero-vad==6.2.3" "faster-whisper==1.2.1" "transformers==5.19.0"
# 3d. av pin LAST and exact: v19 dropped the metadata_errors kwarg that
# faster-whisper 1.2.1 requires; v14 has no cp314 wheels (source build fails).
"$PYBIN" -m pip install "av==15.1.0"
# 3e. Website stack (Starlette TestClient needs httpx).
"$PYBIN" -m pip install \
  "fastapi==0.143.0" "uvicorn==0.54.0" "python-multipart==0.0.32" "httpx==0.28.1"
"$PYBIN" -c "import torch, torchaudio, av; print('torch', torch.__version__, '| torchaudio', torchaudio.__version__, '| av', av.__version__)"

# ---------------------------------------------------------------------------
# Step 4: Ollama + llama3.2 (primary summarizer).
# ---------------------------------------------------------------------------
if [ "$SKIP_OLLAMA" -eq 0 ]; then
  log "Step 4: Ollama"
  OLLAMA=""
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA="ollama"
  else
    for cand in "$LOCALAPPDATA/Programs/Ollama/ollama.exe" \
                "/c/Program Files/Ollama/ollama.exe"; do
      if [ -x "$cand" ]; then OLLAMA="$cand"; break; fi
    done
    if [ -z "$OLLAMA" ]; then
      if command -v winget >/dev/null 2>&1; then
        log "Installing Ollama via winget (user scope)"
        winget install -e --id Ollama.Ollama --scope user \
          --accept-package-agreements --accept-source-agreements --silent \
          || fail "winget Ollama install failed; install from ollama.com by hand"
        hash -r
        for cand in "$LOCALAPPDATA/Programs/Ollama/ollama.exe" \
                    "/c/Program Files/Ollama/ollama.exe"; do
          if [ -x "$cand" ]; then OLLAMA="$cand"; break; fi
        done
      fi
      [ -z "$OLLAMA" ] && [ -x "$LOCALAPPDATA/Programs/Ollama/ollama.exe" ] \
        && OLLAMA="$LOCALAPPDATA/Programs/Ollama/ollama.exe"
      [ -z "$OLLAMA" ] && fail "ollama binary not found; install from ollama.com and re-run"
    fi
  fi
  "$OLLAMA" --version
  if ! "$OLLAMA" list >/dev/null 2>&1; then
    log "Starting ollama serve in the background"
    # shellcheck disable=SC2094
    nohup "$OLLAMA" serve >"$REPO_ROOT/.ollama-bootstrap.log" 2>&1 &
    for _ in $(seq 1 15); do
      sleep 4
      "$OLLAMA" list >/dev/null 2>&1 && break
    done
  fi
  "$OLLAMA" list >/dev/null 2>&1 || fail "ollama serve did not come up; see .ollama-bootstrap.log"
  if ! "$OLLAMA" list 2>/dev/null | grep -qi "llama3.2"; then
    log "Pulling llama3.2 (~2 GB)"
    "$OLLAMA" pull llama3.2 || fail "llama3.2 pull failed; retry later and re-run"
  fi
  "$OLLAMA" list
else
  log "Step 4: Ollama skipped (--skip-ollama)"
fi

# ---------------------------------------------------------------------------
# Step 5: sample fixtures (not stored in git).
# ---------------------------------------------------------------------------
if [ "$SKIP_SAMPLES" -eq 0 ]; then
  log "Step 5: sample fixtures"
  if ls test/samples/sample_*.wav >/dev/null 2>&1; then
    log "sample_*.wav already present, skipping rebuild"
  else
    "$PYBIN" scripts/build_samples.py \
      || fail "sample build failed (needs archive.org reachability)"
  fi
else
  log "Step 5: samples skipped (--skip-samples)"
fi

# ---------------------------------------------------------------------------
# Step 6: model warmup + verification.
# ---------------------------------------------------------------------------
if [ "$SKIP_MODELS" -eq 0 ]; then
  if [ ! -f test/samples/sample_03.wav ]; then
    warn "no sample_03.wav present; skipping model warmup (re-run without --skip-samples)"
  else
  log "Step 6: model warmup (~230 MB: HTDemucs + faster-whisper-base)"
  mkdir -p .bootstrap-tmp
  "$PYBIN" -c "
import sys; sys.path.insert(0, '.')
from audio import ffmpeg_io, separate, transcribe, vad
x = ffmpeg_io.load_mono_wav('test/samples/sample_03.wav')[:30*48000]
ffmpeg_io.write_wav('.bootstrap-tmp/smoke.wav', x)
segs = vad.SileroVAD().segments(x)
print('silero segments:', len(segs))
v, b, m = separate.DemucsSeparator().separate(x)
print('demucs:', m)
r = transcribe.faster_whisper_transcribe('.bootstrap-tmp/smoke.wav', '.bootstrap-tmp/smoke_out')
print('whisper:', r['method'], r['n_segments'])
" || fail "model warmup failed"
  rm -rf .bootstrap-tmp
  fi
else
  log "Step 6: model warmup skipped (--skip-models)"
fi

log "Step 7: test suite"
"$PYBIN" -m pytest tests/ -q || fail "pytest failures; see output above"

if [ "$VERIFY_FULL" -eq 1 ]; then
  log "Step 8: full sample_03 pipeline (~20 min CPU)"
  "$PYBIN" scripts/run_audio_pipeline.py --wav test/samples/sample_03.wav --trigger corpus \
    || fail "pipeline run failed"
  latest="$(ls -dt storage/processed/*/ | head -1)"
  "$PYBIN" scripts/verify_remix.py "$latest" || fail "remix verification failed"
fi

log "Bootstrap complete. Versions:"
"$PYBIN" --version
"$PYBIN" -m pip list --format=freeze 2>/dev/null | grep -Ei "^(torch|torchaudio|demucs|silero-vad|faster-whisper|transformers|av|numpy|soundfile|imageio-ffmpeg|fastapi|uvicorn|pytest)=="
if [ "$SKIP_OLLAMA" -eq 0 ] && [ -n "${OLLAMA:-}" ]; then "$OLLAMA" list; fi
