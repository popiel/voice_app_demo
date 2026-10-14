# Bootstrap: Windows 11 dev machine for voice_app_demo

Automated path: `./scripts/bootstrap_windows.sh` (Git Bash, from repo root).
This doc covers what the script does, what it can't do, and how to recover
when a step fails. Everything is per-user (no admin) and CPU-only.

## 0. By hand first (the script cannot do these)

1. Install **Git for Windows** (gives you git *and* Git Bash — the script
   requires a Bash shell).
2. `git clone <repo-url>` and `cd voice_app_demo`.
3. Check the basics: open internet (PyPI, Hugging Face, archive.org, Ollama
   CDN — configure proxy for all three if behind one), **≥12 GB free disk**.

## 1. What the script does, in order

| # | Step | Notes |
|---|---|---|
| 1 | Python 3.14.x | Uses existing `python3` if 3.14, else known per-user paths, else `winget install Python.Python.3.14` (user scope). Aborts on other versions: `av==15.1.0` has no wheels outside cp314. |
| 2 | Env vars | `PYTHONUTF8=1` (required: non-ASCII catalog data crashes cp1252 consoles) + `HF_HUB_DISABLE_SYMLINKS_WARNING=1`, exported and persisted via `setx`. |
| 3 | pip stack (pinned) | `pip install -U pip`, then: DSP core → torch CPU pair → ML stages → `av` pin → website stack. Order matters, see §3. |
| 4 | Ollama + llama3.2 | Finds the binary (PATH, then per-user install dir), else winget; starts `ollama serve` in background; pulls `llama3.2` (~2 GB). |
| 5 | Sample fixtures | Skips if `test/samples/sample_*.wav` exist (they are **not in git**); else rebuilds via `scripts/build_samples.py` (needs archive.org). |
| 6 | Model warmup | 30 s smoke run that downloads HTDemucs (~84 MB) + faster-whisper-base (~145 MB). Silero weights ship inside the pip package. |
| 7 | `pytest tests/` | Must pass fully. |
| 8 | `--verify-full` only | Full sample_03 pipeline (~20 min CPU) + `verify_remix.py`. |

Re-running is safe: every long step checks first and skips when done.
Use `--skip-python/ollama/models/samples` to defer parts; `--help` for flags.

## 2. Pinned versions (verified working set)

| Component | Version | Source / note |
|---|---|---|
| Python | 3.14.x | python.org, per-user, add to PATH |
| pip | 26.1.2 | `python -m pip install -U pip` |
| torch, torchaudio | 2.11.0+cpu, matched pair | `--index-url https://download.pytorch.org/whl/cpu` (default PyPI torch is a multi-GB CUDA build; index torchaudio lags torch, so pin both) |
| demucs / silero-vad / faster-whisper / transformers | 4.1.0 / 6.2.3 / 1.2.1 / 5.19.0 | PyPI (transformers = BART fallback only) |
| av | **exactly 15.1.0** | v19 dropped `metadata_errors` (breaks faster-whisper); v14 has no cp314 wheels |
| numpy / soundfile / imageio-ffmpeg | 2.5.4 / 0.14.0 / 0.6.0 | imageio-ffmpeg = static ffmpeg binary, no system ffmpeg needed |
| fastapi / uvicorn / python-multipart / httpx | 0.143.0 / 0.54.0 / 0.0.32 / 0.28.1 | website stack (TestClient needs httpx) |
| pytest | 9.1.1 | |
| Git | 2.47+ | Git for Windows |
| Ollama | 0.40.3 | per-user installer; **not on PATH** — script checks `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` |
| llama3.2 | latest (`ollama pull llama3.2`) | ~2.0 GB in `~\.ollama` |

## 3. Disk budget (measured)

pip stack ~2.5 GB, Ollama + model ~2.2 GB, HF cache ~0.25 GB,
samples ~0.16 GB, per-job `storage/` ~0.2 GB → keep 12 GB free.

## 4. If a step fails

- **No Python 3.14 / no winget**: install python.org 3.14.x by hand
  (per-user, add to PATH), re-run with `--skip-python`.
- **torch download huge/slow**: you missed the CPU index — the script pins
  it; if running pip by hand, never omit `--index-url .../cpu`.
- **`metadata_errors` TypeError**: `av` floated past 15.x — reinstall
  `av==15.1.0` exactly.
- **Ollama serve won't start**: port 11434 in use (another serve running —
  fine, re-run), or start it in a separate terminal and re-run with
  `--skip-ollama` for install but keep the pull step by running
  `ollama pull llama3.2` manually.
- **Sample build fails**: usually archive.org blocked — copy
  `test/samples/*.wav` + `provenance.json` + `ATTRIBUTION.md` from another
  dev box instead.
- **Bash `python3` resolves to the WindowsApps stub**: verify with
  `python3 -c "import sys; print(sys.executable)"`; use the full
  `...\Python314\python.exe` path.

## 5. Windows gotchas baked into the workflow

- Git Bash `/tmp` and Python's `\tmp` are different directories — always use
  explicit or workspace-relative temp paths.
- HF symlink warnings without Windows Developer Mode are cosmetic.
- `storage/`, model caches, and `test/samples/` are machine-local
  (gitignored/untracked) — every dev box rebuilds or copies them.
- Expected green state: `pytest tests/` all pass; sample_03 pipeline ends
  `status: done` with `n_attenuate: 3, n_harmonic: 1`; `verify_remix.py`
  prints PASS.

## 6. Deliberately NOT automated

- GPU/CUDA setups (CPU path is the verified one; CUDA needs matched
  torch/torchaudio/CUDA-toolkit versions for that specific box).
- Proxy configuration, admin installs, Windows SDK / C toolchains.
- `transformers`/BART weights (~1.6 GB): only needed if Ollama is
  unavailable; install + download on demand.
