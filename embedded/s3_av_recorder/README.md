# XIAO ESP32S3 Sense — 10 s A/V clip recorder

Back-to-back 10-second clips, no gaps. Video as MJPEG in a real AVI container,
audio as separate WAVs. `video/00000.avi` and `audio/00000.wav` cover the same
window.

## Files

| file | role |
|---|---|
| `s3_av_recorder.ino` | boot, shared epoch `t0`, task launch, health log |
| `config.h` | **the only file you should need to edit** |
| `camera_pins.h` | DVP pin map for the Sense board — self-contained, no download needed |
| `avi_writer.{h,cpp}` | RIFF/AVI MJPEG muxer — headers, `movi`, `idx1` |
| `video_capture.{h,cpp}` | camera init + clip task (core 1) |
| `audio_capture.{h,cpp}` | PDM I2S init + WAV clip task (core 0) |
| `wav.{h,cpp}` | 44-byte PCM header |
| `sd_store.{h,cpp}` | mount, wipe-on-boot, FS mutex, `index.csv` |

Keep them all in a folder named `s3_av_recorder/` so the IDE loads them as tabs.

## Build settings

- **Board:** XIAO_ESP32S3 (not generic ESP32S3 Dev Module)
- **PSRAM: OPI PSRAM.** The board default in `boards.txt` is *Disabled*, so this
  is off unless you set it. The sketch runs either way, but see below
- **USB CDC On Boot: Enabled**, or you see no serial output
- **Arduino-ESP32 core 3.x** — the audio path uses the ESP-IDF 5 `i2s_pdm.h` API
- microSD ≤ 32 GB, formatted **FAT32**

## PSRAM: works without it, but costs you

`XIAO_ESP32S3.menu.PSRAM.disabled` is the first entry in the core's `boards.txt`,
which makes it the default. The onboard 8 MB is therefore unused until you pick
**Tools > PSRAM > OPI PSRAM**.

The sketch detects this and falls back instead of refusing to start:

| | PSRAM on | PSRAM off |
|---|---|---|
| framebuffer location | PSRAM | internal DRAM |
| `fb_count` | 2 | 1 |
| `grab_mode` | `GRAB_LATEST` | `GRAB_WHEN_EMPTY` |
| `idx1` table | 600 frames | 200 frames |
| expected fps @ VGA | ~20–25 | ~8–12 |

The frame rate roughly halves because with a single framebuffer the sensor
cannot expose frame N+1 while frame N is being written to the card — capture and
SD write serialise instead of overlapping. In JPEG mode the driver sizes each
framebuffer at `width * height / 5`, so VGA costs 60 KB of internal DRAM and only
one fits alongside the SD buffers, audio DMA and task stacks.

If init still runs out of memory, `video_begin()` steps the resolution down
(VGA → QVGA → QQVGA), calling `esp_camera_deinit()` between attempts, and logs
the resolution it actually achieved. Recording is not affected by any of this
beyond frame rate: the AVI header is written from measured timing, so a 10 fps
clip plays back correctly at 10 fps.

## Why not the wiki's video sketch

The Seeed wiki's `record_video` example opens a `.avi` and writes raw
`fb->buf` bytes back to back. There is no RIFF header, no stream header, and no
index — just concatenated JPEGs with an `.avi` extension. The wiki's own note
that "the video may open for only one second" is this bug, not a property of
static scenes: nothing in the file tells the player how many frames exist or how
fast to play them, so it guesses, and most players simply refuse to open it.

`avi_writer.cpp` writes the actual container:

```
RIFF/AVI
  LIST hdrl
    avih                 (frame count, µs/frame, suggested buffer)
    LIST strl
      strh 'vids'/'MJPG' (dwRate / dwScale = true fps)
      strf BITMAPINFOHEADER
  LIST movi
    00dc <len> <jpeg> [pad]   ...
  idx1                   (16 B/frame, keyframe flag, offset, length)
```

**Frame rate is measured, not assumed.** Rate-dependent fields are written as
placeholders, and `avi_close()` seeks back and patches them from the actual
frame count and wall-clock span. `dwScale = elapsed_ms`, `dwRate = frames*1000`
gives the exact ratio with no rounding. That's the difference between a clip
that plays at real speed and one that plays at whatever the player invents.

## Running headless / on battery

No serial host is required, and nothing waits for one.

The trap this avoids: with **USB CDC On Boot** enabled, `Serial` is the native
USB peripheral, not a UART. With no host attached its TX buffer fills and never
drains, so `Serial.printf()` blocks forever. The board then works perfectly over
USB and appears dead on a battery. `Serial.setTxTimeoutMs(0)` in
`serial_begin_nonblocking()` makes those writes discard instead of block.

Also changed for unattended use:

- **Nothing halts.** Init failures back off and `ESP.restart()` instead of
  spinning forever — a halted board is indistinguishable from a dead one with no
  serial attached, and would not recover from a card that was merely slow.
- **Each subsystem is retried `INIT_RETRIES` times** with escalating delay, and
  `POWER_SETTLE_MS` runs before the first attempt. External supplies ramp 3V3
  more slowly than USB, so a first-attempt camera or SD failure is common.
- **Stall watchdog.** If no clip is written for `STALL_REBOOT_PERIODS` × 30 s,
  the board restarts itself. Set to 0 to disable.
- **The card is wiped only on a true power-on** (`ESP_RST_POWERON`). A
  self-restart keeps existing recordings and resumes numbering one past the
  highest clip on the card, so recovery never destroys or overwrites a session.

Without serial, the **orange LED is your status light**: SD chip-select shares
GPIO21 with it, so it flickers on every card write. Steady flickering means
clips are being written. Dark means the recorder is not running.

## Data format

```
/video/00000.avi   640x480 MJPEG, ~20-25 fps, 10 s
/audio/00000.wav   16 kHz mono 16-bit PCM, exactly 10 s
/index.csv         kind,index,rel_ms,bytes,frames,millifps
```

`millifps` is fps × 1000, logged per clip so you can spot a card that's
throttling before it starts dropping frames.

To mux a pair afterwards:

```bash
ffmpeg -i video/00000.avi -i audio/00000.wav -c:v copy -c:a aac out.mp4
```

## Design notes

- **One epoch, two clocks.** The video task schedules clip boundaries against
  absolute deadlines from `t0`, so boundaries never drift. The audio task is
  driven by I2S sample count, so each WAV is exactly 10 s of audio regardless of
  SD stalls. They differ by I2S PLL vs system clock error — tens of ppm.
- **Both tasks share one FAT volume**, so every open/write/close goes through the
  mutex in `sd_store`. Audio runs at priority 5 on core 0 with ~0.5 s of DMA
  cushion; a 20 KB JPEG write holds the card for ~20 ms, well inside that.
- **`CAMERA_GRAB_LATEST` with 2 framebuffers.** With `GRAB_WHEN_EMPTY` a slow SD
  write leaves a stale frame queued and the clip comes out temporally lumpy.
- **Clip length uses frame span, not the nominal 10 s.** If the last frame lands
  at 9.83 s the clip really is 9.83 s, and one frame interval is added back
  because N frames occupy N display intervals, not N−1.
- **`idx1` lives in PSRAM** (`VIDEO_MAX_FRAMES × 16` = 9.6 KB) so it never
  competes for the internal DRAM that WiFi will want later.

## Budget

VGA q12 ≈ 15–25 KB/frame. At ~22 fps that's ~400 KB/s video + 32 KB/s audio,
so roughly **4.3 MB per clip** and **~1.5 GB/hour**. A 32 GB card holds about
**20 hours**.

## Tuning

| symptom | fix |
|---|---|
| fps far below 20 | `CAM_JPEG_QUALITY` 12 → 18, or drop `SD_SPI_HZ` isn't it — try a faster card (A1/U3) |
| SD mount fails / CRC errors | drop `SD_SPI_HZ` to 10000000 |
| "idx table full" in the log | raise `VIDEO_MAX_FRAMES` |
| WAVs silent | swap `MIC_PIN_CLK` / `MIC_PIN_DATA`, or try `I2S_SLOT_MODE_STEREO` |
| audio too quiet | raise `AUDIO_GAIN_SHIFT` (2 → 4) |
| video only, no mic | `CAPTURE_AUDIO 0` in `config.h` |

## Next stages

1. dB-threshold gating on audio — breaks the tidy 1:1 clip pairing, so
   `index.csv` becomes mandatory rather than advisory.
2. BLE provisioning (NimBLE) → SSID/PSK into NVS.
3. WiFi sync — walk `index.csv`, POST each artifact, mark uploaded, delete.
   Add a session counter in NVS once you stop wiping on boot.
