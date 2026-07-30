/* =========================================================================
 *  XIAO ESP32S3 Sense — continuous 10 s A/V clip recorder
 *
 *  Video : MJPEG in a real AVI container -> /video/NNNNN.avi
 *  Audio : 16 kHz mono PCM               -> /audio/NNNNN.wav
 *  Index : /index.csv
 *
 *  Runs headless. No serial host is required at any point, and nothing
 *  blocks waiting for one. See "HEADLESS OPERATION" below.
 * ========================================================================= */

#include <esp_system.h>

#include "config.h"
#include "sd_store.h"
#include "video_capture.h"
#include "audio_capture.h"

/* Survives soft resets (not power cycles), so escalating backoff is not
   forgotten every time we restart ourselves. */
RTC_DATA_ATTR static uint32_t s_boot_failures = 0;

/* -------------------------------------------------------------------------
 *  HEADLESS OPERATION
 *
 *  With USB CDC On Boot enabled, `Serial` is the native USB peripheral, not a
 *  UART. If no host is attached the TX buffer fills and never drains, and
 *  Serial.printf() blocks forever waiting for a reader. That is why the board
 *  works on USB and stalls on a battery.
 *
 *  setTxTimeoutMs(0) makes those writes discard instead of block when no host
 *  is present, which is the single change that makes this run headless.
 * ---------------------------------------------------------------------- */
static void serial_begin_nonblocking() {
  Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);
#endif
  /* Brief, bounded grace period so a host that IS attached catches the boot
     banner. Never waits on !Serial, so an unattended board loses nothing. */
  uint32_t deadline = millis() + 400;
  while (!Serial && (int32_t)(millis() - deadline) < 0) delay(10);
  delay(50);
}

/* Retry an init step instead of dying on the first attempt. On external power
   the rails ramp more slowly than over USB, so the SD card and camera can
   legitimately need a second try. */
static bool init_retry(bool (*fn)(), const char *what, uint8_t tries) {
  for (uint8_t i = 1; i <= tries; i++) {
    if (fn()) return true;
    Serial.printf("[boot] %s failed (attempt %u/%u)\n", what, i, tries);
    delay(300u * i);
  }
  return false;
}

/* Never halt. A halted board is indistinguishable from a dead one when there
   is no serial attached, and it will not recover if the card was merely slow
   or was inserted late. Back off, then reboot and try the whole thing again. */
static void fail_restart(const char *what) {
  s_boot_failures++;
  uint32_t wait_ms = s_boot_failures * 2000;
  if (wait_ms > 30000) wait_ms = 30000;

  Serial.printf("\n[boot] %s unavailable (failure #%lu) — restarting in %lu ms\n",
                what, (unsigned long)s_boot_failures, (unsigned long)wait_ms);
  Serial.flush();
  delay(wait_ms);
  ESP.restart();
}

void setup() {
  serial_begin_nonblocking();

  Serial.println("\n=== XIAO ESP32S3 Sense A/V recorder ===");
  Serial.printf("[boot] reset reason %d, prior boot failures %lu\n",
                (int)esp_reset_reason(), (unsigned long)s_boot_failures);
  Serial.printf("[boot] PSRAM: %s (%u KB free)\n",
                psramFound() ? "yes" : "no (Tools > PSRAM > OPI PSRAM)",
                (unsigned)(ESP.getFreePsram() / 1024));

  /* Let the 3V3 rail settle before touching the camera or card. Matters on
     battery and on weak USB adapters, costs nothing on a bench supply. */
  delay(POWER_SETTLE_MS);

  if (!init_retry(video_begin, "camera", INIT_RETRIES)) fail_restart("camera");
  if (!init_retry(sd_begin,    "SD card", INIT_RETRIES)) fail_restart("SD card");
  if (!init_retry(audio_begin, "microphone", INIT_RETRIES)) fail_restart("microphone");

  /* Everything is up; clear the backoff so a later fault starts from zero. */
  s_boot_failures = 0;

  uint32_t t0 = millis();
  if (!video_start_task(t0)) fail_restart("video task");
  if (!audio_start_task(t0)) fail_restart("audio task");

  Serial.printf("[boot] recording %lu s clips\n", (unsigned long)(CLIP_MS / 1000));
}

void loop() {
  static uint32_t last = 0;
  static uint32_t last_clips = 0;
  static uint8_t  stalls = 0;

  if (millis() - last < 30000) { delay(100); return; }
  last = millis();

  uint32_t clips = video_clips_saved();

  Serial.printf("[stat] up=%lus  vid=%lu  aud=%lu  fps=%lu.%03lu  heap=%u  psram=%u  free=%lluMB\n",
                (unsigned long)(millis() / 1000),
                (unsigned long)clips,
                (unsigned long)audio_clips_saved(),
                (unsigned long)(video_last_millifps() / 1000),
                (unsigned long)(video_last_millifps() % 1000),
                (unsigned)ESP.getFreeHeap(),
                (unsigned)ESP.getFreePsram(),
                sd_free_bytes() / (1024ULL * 1024ULL));

  /* Headless watchdog. Without serial there is no way to notice that the
     recorder wedged, so detect it here: 30 s should always produce clips. */
  if (clips == last_clips) {
    if (++stalls >= STALL_REBOOT_PERIODS) {
      Serial.println("[stat] no clips written for too long — restarting");
      Serial.flush();
      delay(100);
      ESP.restart();
    }
  } else {
    stalls = 0;
  }
  last_clips = clips;
}
