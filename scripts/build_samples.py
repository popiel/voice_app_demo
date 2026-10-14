"""Build 3 rights-cleared demo samples: LibriVox voice + sporadic Musopen
orchestral bursts mixed at interfering SNR with raised-cosine edges.

Sources (see test/samples/provenance.json):
  voice: LibriVox Short Ghost/Horror Collection Vol. 016 (public domain)
  music: MusopenCollectionAsFlac, Public Domain Mark 1.0 (PD composition + PD recording)

Outputs: test/samples/sample_01..03.wav — 48 kHz mono 16-bit, 3-10 min each.
Deterministic: fixed schedules, seeds, and levels (COR-S-004 / COR-AC-003).
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000
WORKSPACE = Path(__file__).resolve().parent.parent
OUT_DIR = WORKSPACE / "test" / "samples"
TMP = Path(r"C:\Users\tapop\AppData\Local\Temp")

VOICES = {
    "sample_01": str(TMP / "voice1.mp3"),  # Oval Portrait (Poe), reader ep, ~9.4 min
    "sample_02": str(TMP / "voice2.mp3"),  # Xmas Goblins (Dickens), reader bm, ~9.5 min
    "sample_03": str(TMP / "voice3.mp3"),  # A Dark Mirror, reader CC, ~8.7 min
}
BEDS = {
    "sample_01": str(TMP / "music1.flac"),  # Beethoven Coriolan Overture, ~8.3 min
    "sample_02": str(TMP / "music2.flac"),  # Mozart Magic Flute Overture, ~6.7 min
    "sample_03": str(TMP / "music3.flac"),  # Mendelssohn Italian Sym.4-iv, ~6.1 min
}
# (burst_start_s, burst_end_s); music excerpt slices taken sequentially from bed.
BURSTS = {
    "sample_01": [(60, 120), (240, 300), (420, 480)],
    "sample_02": [(30, 75), (200, 260), (380, 440), (500, 545)],
    "sample_03": [(90, 150), (300, 360), (450, 500)],
}
# Music RMS relative to voice RMS inside bursts (dB). ~0 dB => strong interference.
BURST_SNR_DB = {"sample_01": 0.0, "sample_02": 2.0, "sample_03": -2.0}
RAMP_S = 2.0  # raised-cosine edge on each burst (sample construction, not AUD-B-004)


def decode_48k_mono(src: str, dst: Path) -> None:
    cmd = [FFMPEG, "-y", "-v", "error", "-i", src,
           "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", str(dst)]
    subprocess.run(cmd, check=True)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def raised_cosine(n: int) -> np.ndarray:
    t = np.arange(n) / max(n - 1, 1)
    return 0.5 - 0.5 * np.cos(np.pi * t)


def build(name: str) -> dict:
    v_wav = TMP / f"{name}_v48.wav"
    m_wav = TMP / f"{name}_m48.wav"
    decode_48k_mono(VOICES[name], v_wav)
    decode_48k_mono(BEDS[name], m_wav)
    voice, _ = sf.read(str(v_wav), dtype="float32")
    bed, _ = sf.read(str(m_wav), dtype="float32")

    n = len(voice)
    dur = n / SR
    assert 180 <= dur <= 600, f"{name}: voice {dur:.1f}s outside 3-10 min"

    v_rms = rms(voice)
    music = np.zeros(n, dtype=np.float64)
    bed_pos = 0
    for (s0, s1) in BURSTS[name]:
        i0, i1 = int(s0 * SR), min(int(s1 * SR), n)
        L = i1 - i0
        seg = np.zeros(L, dtype=np.float64)
        need = L
        while need > 0:
            take = min(need, len(bed) - bed_pos)
            seg[L - need:L - need + take] = bed[bed_pos:bed_pos + take]
            bed_pos = (bed_pos + take) % len(bed)
            need -= take
        # Level: burst music RMS == voice RMS in that window + SNR offset.
        seg_rms, win_rms = rms(seg), rms(voice[i0:i1])
        gain = win_rms / seg_rms * 10 ** (BURST_SNR_DB[name] / 20)
        seg *= gain
        # Raised-cosine ramps at both edges.
        r = int(RAMP_S * SR)
        seg[:r] *= raised_cosine(r)
        seg[-r:] *= raised_cosine(r)[::-1]
        music[i0:i1] += seg

    mix = voice.astype(np.float64) + music
    mix *= 0.89 / max(np.abs(mix).max(), 1e-9)  # peak to -1 dBFS
    out = OUT_DIR / f"{name}.wav"
    sf.write(str(out), (mix * 32767).astype(np.int16), SR, subtype="PCM_16")
    info = {
        "file": f"{name}.wav",
        "duration_s": round(len(mix) / SR, 1),
        "sample_rate_hz": SR,
        "channels": 1,
        "bursts": [{"start": s0, "end": s1} for s0, s1 in BURSTS[name]],
        "burst_music_snr_db_vs_voice": BURST_SNR_DB[name],
    }
    print(f"{name}: voice {dur:.1f}s, bursts {BURSTS[name]}, "
          f"mix peak {np.abs(mix).max():.3f} -> {out}")
    return info


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = [build(f"sample_{i:02d}") for i in (1, 2, 3)]
    with open(OUT_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("wrote", OUT_DIR / "manifest.json")


if __name__ == "__main__":
    sys.exit(main())
