/* =========================================================================
 *  XIAO ESP32S3 Sense — continuous 10 s A/V clip recorder
 *
 *  Video : MJPEG in a real AVI container -> /video/NNNNN.avi
 *          640x480, frame rate measured at runtime and written into the header
 *  Audio : 16 kHz mono PCM              -> /audio/NNNNN.wav
 *  Index : /index.csv
 *
 *  video/00000.avi and audio/00000.wav cover the same 10 s window.
 *  Set CAPTURE_AUDIO to 0 in config.h for video only.
 * ========================================================================= */

#include "config.h"
#include "sd_store.h"
#include "video_capture.h"
#include "audio_capture.h"

static void fatal(const char *what) {
  Serial.printf("\n[boot] FATAL: %s — halting\n", what);
  for (;;) delay(1000);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n=== XIAO ESP32S3 Sense A/V recorder ===");
  Serial.printf("[boot] PSRAM: %s (%u KB free)\n",
                psramFound() ? "yes" : "NO",
                (unsigned)(ESP.getFreePsram() / 1024));

  if (!video_begin()) fatal("camera");
  if (!sd_begin())    fatal("SD card");
  if (!audio_begin()) fatal("microphone");

  /* One epoch shared by both tasks. Clip N of each stream is aligned to
     t0 + N * CLIP_MS, which is what makes them muxable later. */
  uint32_t t0 = millis();

  if (!video_start_task(t0)) fatal("video task");
  if (!audio_start_task(t0)) fatal("audio task");

  Serial.printf("[boot] recording %lu s clips\n", (unsigned long)(CLIP_MS / 1000));
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last >= 30000) {
    last = millis();
    Serial.printf("[stat] up=%lus  vid=%lu  aud=%lu  fps=%lu.%03lu  heap=%u  psram=%u  free=%lluMB\n",
                  (unsigned long)(millis() / 1000),
                  (unsigned long)video_clips_saved(),
                  (unsigned long)audio_clips_saved(),
                  (unsigned long)(video_last_millifps() / 1000),
                  (unsigned long)(video_last_millifps() % 1000),
                  (unsigned)ESP.getFreeHeap(),
                  (unsigned)ESP.getFreePsram(),
                  sd_free_bytes() / (1024ULL * 1024ULL));
  }
  delay(100);
}
