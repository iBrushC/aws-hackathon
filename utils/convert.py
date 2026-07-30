#!/usr/bin/env python3
"""
xiao_merge.py — turn a XIAO ESP32S3 recorder card into playable A/V clips.

The device writes two parallel streams:

    /video/00000.avi   MJPEG, frame rate measured at capture time
    /audio/00000.wav   16 kHz mono 16-bit PCM
    /index.csv         kind,index,rel_ms,bytes,frames,millifps

Matching indices cover the same wall-clock window, so merging is a pairwise
mux. Video is passed through untouched by default (-c:v copy): no re-encode,
no generation loss, and it runs far faster than real time.

    python3 xiao_merge.py /media/sdcard -o ./clips
    python3 xiao_merge.py /media/sdcard -o ./clips --reencode
    python3 xiao_merge.py /media/sdcard -o ./clips --concat session.mp4

Requires ffmpeg on PATH.
"""

import argparse
import csv
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# RIFF / AVI parsing
#
# Offsets below are relative to each chunk's DATA start (chunk_off + 8), not to
# the file, so they stay correct even if the header layout shifts.
# ---------------------------------------------------------------------------

AVIH_WIDTH, AVIH_HEIGHT = 32, 36
AVIH_TOTAL_FRAMES = 16
STRH_SCALE, STRH_RATE, STRH_LENGTH = 20, 24, 32
STRH_RC_RIGHT, STRH_RC_BOTTOM = 52, 54
BIH_WIDTH, BIH_HEIGHT, BIH_SIZEIMAGE = 4, 8, 20


@dataclass
class AviInfo:
    path: Path
    width: int = 0
    height: int = 0
    frames: int = 0
    scale: int = 1
    rate: int = 1
    avih_off: int = 0          # data offset of avih
    strh_off: int = 0          # data offset of video strh
    strf_off: int = 0          # data offset of video strf
    movi_off: int = 0          # file offset of the 'movi' FOURCC
    size: int = 0

    @property
    def fps(self) -> float:
        return self.rate / self.scale if self.scale else 0.0

    @property
    def duration(self) -> float:
        return self.frames / self.fps if self.fps else 0.0


def _chunks(buf: bytes, start: int, end: int):
    """Yield (fourcc, data_offset, size) for chunks in [start, end)."""
    off = start
    while off + 8 <= end and off + 8 <= len(buf):
        ckid = buf[off:off + 4]
        size = struct.unpack_from("<I", buf, off + 4)[0]
        yield ckid, off + 8, size
        off += 8 + size + (size & 1)


def read_avi(path: Path) -> AviInfo:
    """Parse enough of the AVI to validate it and locate patchable fields."""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        head = fh.read(min(size, 65536))

    if len(head) < 32 or head[0:4] != b"RIFF" or head[8:12] != b"AVI ":
        raise ValueError("not a RIFF/AVI file")

    info = AviInfo(path=path, size=size)
    riff_end = min(len(head), 8 + struct.unpack_from("<I", head, 4)[0])

    for ckid, doff, csize in _chunks(head, 12, riff_end):
        if ckid == b"LIST" and head[doff:doff + 4] == b"hdrl":
            _parse_hdrl(head, doff + 4, doff + csize, info)
        elif ckid == b"LIST" and head[doff:doff + 4] == b"movi":
            info.movi_off = doff          # points at the 'movi' FOURCC
            break

    if not info.avih_off:
        raise ValueError("no avih chunk")
    if not info.movi_off:
        raise ValueError("no movi list")
    return info


def _parse_hdrl(buf: bytes, start: int, end: int, info: AviInfo) -> None:
    for ckid, doff, csize in _chunks(buf, start, end):
        if ckid == b"avih":
            info.avih_off = doff
            info.width = struct.unpack_from("<I", buf, doff + AVIH_WIDTH)[0]
            info.height = struct.unpack_from("<I", buf, doff + AVIH_HEIGHT)[0]
            info.frames = struct.unpack_from("<I", buf, doff + AVIH_TOTAL_FRAMES)[0]
        elif ckid == b"LIST" and buf[doff:doff + 4] == b"strl":
            _parse_strl(buf, doff + 4, doff + csize, info)


def _parse_strl(buf: bytes, start: int, end: int, info: AviInfo) -> None:
    strh_off = strf_off = 0
    is_video = False
    for ckid, doff, csize in _chunks(buf, start, end):
        if ckid == b"strh":
            strh_off = doff
            is_video = buf[doff:doff + 4] == b"vids"
        elif ckid == b"strf":
            strf_off = doff

    if is_video and not info.strh_off:          # first video stream wins
        info.strh_off = strh_off
        info.strf_off = strf_off
        info.scale = struct.unpack_from("<I", buf, strh_off + STRH_SCALE)[0] or 1
        info.rate = struct.unpack_from("<I", buf, strh_off + STRH_RATE)[0] or 1


# ---------------------------------------------------------------------------
# JPEG dimension recovery
#
# Firmware before the header-patch fix wrote 0x0 into every dimension field.
# The JPEG payload always carries the true size in its SOF marker, so such
# files are repairable in place rather than lost.
# ---------------------------------------------------------------------------

# SOF0..SOF15, excluding DHT (C4), JPG (C8) and DAC (CC), which are not frames.
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_dimensions(data: bytes):
    """(width, height) from the first SOF marker, or None."""
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xD9:                     # EOI
            break
        seglen = struct.unpack_from(">H", data, i + 2)[0]
        if marker in SOF_MARKERS:
            if i + 9 > n:
                break
            height = struct.unpack_from(">H", data, i + 5)[0]
            width = struct.unpack_from(">H", data, i + 7)[0]
            return width, height
        i += 2 + seglen
    return None


def first_frame_dims(info: AviInfo):
    """Read the first 00dc chunk and pull dimensions out of the JPEG."""
    with open(info.path, "rb") as fh:
        fh.seek(info.movi_off + 4)             # skip the 'movi' FOURCC
        header = fh.read(8)
        if len(header) < 8:
            return None
        ckid, csize = header[0:4], struct.unpack_from("<I", header, 4)[0]
        if not ckid.endswith(b"dc"):
            return None
        return jpeg_dimensions(fh.read(min(csize, 65536)))


def repair_avi(info: AviInfo) -> bool:
    """Patch zeroed dimensions in place. Returns True if the file was changed."""
    if info.width and info.height:
        return False
    dims = first_frame_dims(info)
    if not dims:
        return False
    w, h = dims

    with open(info.path, "r+b") as fh:
        def p32(off, val):
            fh.seek(off)
            fh.write(struct.pack("<I", val))

        def p16(off, val):
            fh.seek(off)
            fh.write(struct.pack("<H", val))

        p32(info.avih_off + AVIH_WIDTH, w)
        p32(info.avih_off + AVIH_HEIGHT, h)
        if info.strh_off:
            p16(info.strh_off + STRH_RC_RIGHT, w)
            p16(info.strh_off + STRH_RC_BOTTOM, h)
        if info.strf_off:
            p32(info.strf_off + BIH_WIDTH, w)
            p32(info.strf_off + BIH_HEIGHT, h)
            p32(info.strf_off + BIH_SIZEIMAGE, w * h * 3)

    info.width, info.height = w, h
    return True


# ---------------------------------------------------------------------------
# WAV inspection
#
# Three failure modes look identical in a player ("no sound"), so separate
# them here: WAV absent, WAV present but digitally silent (a mic/PDM problem
# on the device), or WAV fine (a muxing problem on this side).
# ---------------------------------------------------------------------------

@dataclass
class WavInfo:
    path: Path
    rate: int = 0
    channels: int = 0
    bits: int = 0
    frames: int = 0
    peak: int = 0
    rms: float = 0.0
    error: str = ""

    @property
    def duration(self) -> float:
        return self.frames / self.rate if self.rate else 0.0

    @property
    def silent(self) -> bool:
        return not self.error and self.frames > 0 and self.peak == 0

    @property
    def near_silent(self) -> bool:
        # 16-bit full scale is 32768; a peak under ~0.4% of that is unusable
        return not self.error and self.frames > 0 and 0 < self.peak < 128


def inspect_wav(path: Path, max_samples: int = 2_000_000) -> WavInfo:
    import wave as _wave
    info = WavInfo(path=path)
    try:
        with _wave.open(str(path), "rb") as wv:
            info.channels = wv.getnchannels()
            info.bits = wv.getsampwidth() * 8
            info.rate = wv.getframerate()
            info.frames = wv.getnframes()
            if info.frames == 0:
                return info
            raw = wv.readframes(min(info.frames, max_samples))
    except Exception as exc:                      # noqa: BLE001 - report, do not raise
        info.error = f"unreadable: {exc}"
        return info

    if info.bits == 16:
        n = len(raw) // 2
        if n:
            vals = struct.unpack(f"<{n}h", raw[:n * 2])
            info.peak = max(max(vals), -min(vals))
            info.rms = (sum(v * v for v in vals) / n) ** 0.5
    else:
        info.peak = max(raw) - 128 if raw else 0
    return info


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

INDEX_RE = re.compile(r"(\d+)")


@dataclass
class Pair:
    index: int
    video: Path
    audio: Path = None
    info: AviInfo = None
    wav: "WavInfo" = None
    repaired: bool = False
    note: str = ""


def _indexed(directory: Path, suffix: str) -> dict:
    out = {}
    if not directory.is_dir():
        return out
    for p in sorted(directory.iterdir()):
        if p.suffix.lower() != suffix or not p.is_file():
            continue
        m = INDEX_RE.search(p.stem)
        if m:
            out[int(m.group(1))] = p
    return out


def discover(root: Path) -> list:
    videos = _indexed(root / "video", ".avi")
    audios = _indexed(root / "audio", ".wav")
    if not videos:
        raise SystemExit(f"no .avi files found under {root / 'video'}")

    pairs = []
    for idx in sorted(videos):
        pairs.append(Pair(index=idx, video=videos[idx], audio=audios.get(idx)))
    return pairs


def read_index_csv(root: Path) -> dict:
    """Optional. Used only for reporting, never for pairing."""
    path = root / "index.csv"
    rows = {"video": {}, "audio": {}}
    if not path.is_file():
        return rows
    try:
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                kind = row.get("kind")
                if kind in rows:
                    rows[kind][int(row["index"])] = row
    except (OSError, ValueError, KeyError):
        pass
    return rows


# ---------------------------------------------------------------------------
# Muxing
# ---------------------------------------------------------------------------

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def mux(pair: Pair, outdir: Path, container: str, copy: bool,
        crf: int, shortest: bool, overwrite: bool,
        silent_fill: bool = True, rate: int = 16000) -> tuple:
    out = outdir / f"{pair.index:05d}.{container}"
    if out.exists() and not overwrite:
        return pair, True, "exists, skipped"

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(pair.video)]

    # A clip with no WAV would otherwise have one stream while its neighbours
    # have two. The concat demuxer requires identical layouts and silently
    # DROPS mismatched inputs, so fill the hole with silence instead.
    fill = pair.audio is None and silent_fill
    if pair.audio:
        cmd += ["-i", str(pair.audio)]
    elif fill:
        cmd += ["-f", "lavfi", "-i",
                f"anullsrc=channel_layout=mono:sample_rate={rate}"]

    cmd += ["-map", "0:v:0"]
    if pair.audio or fill:
        cmd += ["-map", "1:a:0"]

    if copy:
        # MJPEG has no valid tag in MP4 — the muxer rejects 'jpeg' and 'mp4v'
        # mislabels it as MPEG-4 Visual. main() redirects --copy to Matroska.
        cmd += ["-c:v", "copy"]
    else:
        # H.264 + yuv420p + faststart is what actually plays everywhere:
        # QuickLook, Explorer thumbnails, browsers, phones.
        # The scale filter rounds odd dimensions down; libx264 cannot encode
        # odd sizes in yuv420p and would abort.
        cmd += ["-c:v", "libx264", "-crf", str(crf),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-pix_fmt", "yuv420p", "-preset", "veryfast"]

    if pair.audio or fill:
        # PCM survives in Matroska; MP4 needs a codec it can carry.
        cmd += ["-c:a", "pcm_s16le"] if container == "mkv" else \
               ["-c:a", "aac", "-b:a", "96k"]

    # anullsrc is infinite, so it must be bounded by the video length.
    if fill or (shortest and pair.audio):
        cmd += ["-shortest"]

    # Move the index to the front so players can start without reading the
    # whole file. This is what makes OS thumbnailers generate a preview.
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]

    cmd += [str(out)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        return pair, False, err[-1] if err else "ffmpeg failed"

    # Close the loop: confirm the track we asked for actually landed. A mux
    # can succeed while quietly dropping a stream.
    layout = _stream_layout(out)
    if (pair.audio or fill) and "aac" not in layout and "pcm" not in layout:
        return pair, False, f"audio stream missing from output ({layout})"
    return pair, True, ""


def _stream_layout(path: Path) -> str:
    """Codec signature, e.g. 'mjpeg+aac'. Used to detect concat mismatches."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    return "+".join(s.strip() for s in proc.stdout.split() if s.strip())


def concat(outdir: Path, container: str, target: Path) -> bool:
    """Join the per-clip outputs into one timeline with the concat demuxer."""
    clips = sorted(outdir.glob(f"*.{container}"))
    clips = [c for c in clips if c.resolve() != target.resolve()]
    if not clips:
        return False

    # The concat demuxer drops inputs whose stream layout differs from the
    # first, without an error and without a non-zero exit code. Check first,
    # or the joined file is quietly short.
    layouts = {}
    for c in clips:
        layouts.setdefault(_stream_layout(c), []).append(c.name)
    if len(layouts) > 1:
        sys.stderr.write("refusing to concat: clips have different streams\n")
        for sig, names in sorted(layouts.items()):
            preview = ", ".join(names[:5]) + (" ..." if len(names) > 5 else "")
            sys.stderr.write(f"    {sig or '(none)'}: {len(names)} [{preview}]\n")
        sys.stderr.write("    re-run without --no-silent-fill to make them uniform\n")
        return False

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for c in clips:
            fh.write(f"file '{c.resolve().as_posix()}'\n")
        listfile = fh.name

    try:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "concat", "-safe", "0", "-i", listfile,
               "-c", "copy", str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.stderr.write((proc.stderr or "").strip() + "\n")
            return False
        return True
    finally:
        os.unlink(listfile)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge XIAO ESP32S3 recorder AVI+WAV pairs into clips.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("root", type=Path,
                    help="SD card root (the folder containing video/ and audio/)")
    ap.add_argument("-o", "--out", type=Path, default=Path("./clips"),
                    help="output directory (default: ./clips)")
    ap.add_argument("--container", choices=("mp4", "mkv"), default="mp4",
                    help="output container (default: mp4)")
    ap.add_argument("--copy", action="store_true",
                    help="stream-copy the MJPEG instead of encoding H.264. "
                         "Fast and lossless, but MJPEG in MP4 is tagged as "
                         "MPEG-4 Visual and many players refuse it — pair "
                         "with --container mkv if you use this")
    ap.add_argument("--reencode", action="store_true",
                    help=argparse.SUPPRESS)   # accepted, now the default
    ap.add_argument("--crf", type=int, default=23,
                    help="H.264 quality, lower is better (default: 23)")
    ap.add_argument("--no-silent-fill", action="store_true",
                    help="leave clips with no WAV as video-only instead of "
                         "padding with silence (breaks --concat)")
    ap.add_argument("--shortest", action="store_true",
                    help="truncate each clip to the shorter stream")
    ap.add_argument("--no-repair", action="store_true",
                    help="do not patch AVIs that have zeroed dimensions")
    ap.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 4,
                    help="parallel ffmpeg processes")
    ap.add_argument("--concat", type=Path, metavar="FILE",
                    help="also join every clip into one file")
    ap.add_argument("--overwrite", action="store_true",
                    help="rewrite outputs that already exist")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="inspect and report only, including per-clip audio "
                         "levels; implies --dry-run")
    args = ap.parse_args()
    if args.check:
        args.dry_run = True

    if not ffmpeg_available():
        sys.stderr.write("error: ffmpeg not found on PATH\n")
        return 2
    if not args.root.is_dir():
        sys.stderr.write(f"error: {args.root} is not a directory\n")
        return 2

    pairs = discover(args.root)
    index_rows = read_index_csv(args.root)

    # ---- inspect, and repair zeroed dimensions before handing to ffmpeg ----
    usable, broken = [], []
    for p in pairs:
        try:
            p.info = read_avi(p.video)
        except ValueError as exc:
            p.note = str(exc)
            broken.append(p)
            continue

        if p.info.frames == 0:
            p.note = "no frames"
            broken.append(p)
            continue

        if not (p.info.width and p.info.height):
            if args.no_repair or args.dry_run:
                p.note = "zeroed dimensions (needs repair)"
            else:
                p.repaired = repair_avi(p.info)
                p.note = "repaired dimensions" if p.repaired else \
                         "zeroed dimensions, unrecoverable"
            if not (p.info.width and p.info.height):
                broken.append(p)
                continue
        if p.audio:
            p.wav = inspect_wav(p.audio)
        usable.append(p)

    # ---- report ----
    print(f"found {len(pairs)} clips under {args.root}")
    missing_audio = [p.index for p in usable if p.audio is None]
    repaired = [p.index for p in usable if p.repaired]

    if usable:
        fps = [p.info.fps for p in usable if p.info.fps]
        dur = sum(p.info.duration for p in usable)
        dims = {(p.info.width, p.info.height) for p in usable}
        print(f"  resolution : {', '.join(f'{w}x{h}' for w, h in sorted(dims))}")
        if fps:
            print(f"  frame rate : {min(fps):.2f}–{max(fps):.2f} fps "
                  f"(mean {sum(fps) / len(fps):.2f})")
        print(f"  video time : {dur:.1f} s across {len(usable)} clips")
    if repaired:
        print(f"  repaired   : {len(repaired)} file(s) with zeroed dimensions")
    if missing_audio:
        preview = ", ".join(str(i) for i in missing_audio[:8])
        more = " ..." if len(missing_audio) > 8 else ""
        how = "left video-only" if args.no_silent_fill else "PADDED WITH SILENCE"
        print(f"  no audio   : {len(missing_audio)} clip(s) [{preview}{more}] — {how}")

    withwav = [p for p in usable if p.wav]
    if withwav:
        bad = [p for p in withwav if p.wav.error]
        silent = [p for p in withwav if p.wav.silent]
        quiet = [p for p in withwav if p.wav.near_silent]
        ok_wavs = [p for p in withwav if not (p.wav.error or p.wav.silent)]
        w0 = withwav[0].wav
        print(f"  audio      : {len(withwav)} wav(s), "
              f"{w0.rate} Hz {w0.channels}ch {w0.bits}-bit")
        if ok_wavs:
            pk = max(p.wav.peak for p in ok_wavs)
            rm = sum(p.wav.rms for p in ok_wavs) / len(ok_wavs)
            print(f"               peak {pk} / 32768 ({100*pk/32768:.1f}% FS), "
                  f"mean rms {rm:.0f}")
        if bad:
            print(f"               {len(bad)} unreadable: {bad[0].wav.error}")
        if silent:
            print(f"               !! {len(silent)} wav(s) are DIGITALLY SILENT "
                  f"(every sample zero)")
            print(f"               that is a microphone problem on the device, "
                  f"not a merge problem")
        elif quiet:
            print(f"               !! {len(quiet)} wav(s) barely above zero "
                  f"— raise AUDIO_GAIN_SHIFT in config.h")
    if broken:
        print(f"  unusable   : {len(broken)} clip(s)")
        for p in broken[:8]:
            print(f"      {p.video.name}: {p.note}")

    # gaps in the index sequence mean lost clips, worth surfacing
    if usable:
        seen = {p.index for p in pairs}
        gaps = sorted(set(range(min(seen), max(seen) + 1)) - seen)
        if gaps:
            preview = ", ".join(str(i) for i in gaps[:8])
            more = " ..." if len(gaps) > 8 else ""
            print(f"  gaps       : {len(gaps)} missing index(es) [{preview}{more}]")

    if index_rows["video"]:
        logged = len(index_rows["video"])
        if logged != len(pairs):
            print(f"  note       : index.csv lists {logged} video clips, "
                  f"{len(pairs)} present on disk")

    if not usable:
        sys.stderr.write("nothing to merge\n")
        return 1

    if args.check:
        print("\n  idx   frames    fps   video s   audio s      peak    rms")
        for p in usable:
            w = p.wav
            if w and not w.error:
                a = f"{w.duration:8.2f}  {w.peak:8d}  {w.rms:6.0f}"
            elif w:
                a = f"{'error':>8}  {'':>8}  {'':>6}"
            else:
                a = f"{'none':>8}  {'':>8}  {'':>6}"
            print(f"  {p.index:5d} {p.info.frames:6d} {p.info.fps:6.2f} "
                  f"{p.info.duration:9.2f}  {a}")
        return 0

    if args.dry_run:
        print(f"\ndry run: would write {len(usable)} clip(s) to {args.out}")
        return 0

    # ---- mux ----
    args.out.mkdir(parents=True, exist_ok=True)
    codec = "MJPEG copy" if args.copy else f"H.264 crf {args.crf}"
    if args.copy and args.container == "mp4":
        # ffmpeg's MP4 muxer cannot carry MJPEG: 'mp4v' mislabels it and the
        # correct 'jpeg' tag is rejected, yielding a 0-byte file. Matroska
        # takes it without complaint, so switch rather than fail.
        args.container = "mkv"
        print("  note: MP4 cannot carry MJPEG — using .mkv for --copy")
    print(f"\nmerging {len(usable)} clip(s) -> {args.out} "
          f"({codec}, .{args.container})")

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(mux, p, args.out, args.container,
                               args.copy, args.crf, args.shortest,
                               args.overwrite, not args.no_silent_fill)
                   for p in usable]
        for fut in futures:
            pair, good, msg = fut.result()
            if good:
                ok += 1
                if msg:
                    print(f"  {pair.index:05d}: {msg}")
            else:
                failed += 1
                print(f"  {pair.index:05d}: FAILED — {msg}")

    print(f"\n{ok} clip(s) written, {failed} failed")

    if args.concat:
        print(f"joining into {args.concat} ...")
        if concat(args.out, args.container, args.concat):
            print(f"wrote {args.concat}")
        else:
            sys.stderr.write("concat failed\n")
            return 1

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
