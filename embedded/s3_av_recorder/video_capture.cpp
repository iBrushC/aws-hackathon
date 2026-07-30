#include "video_capture.h"
#include "config.h"
#include "sd_store.h"
#include "avi_writer.h"

#include "esp_camera.h"
#include "camera_pins.h"

static uint32_t s_t0 = 0;
static volatile uint32_t s_clips = 0;
static volatile uint32_t s_millifps = 0;
static bool s_have_psram = false;

uint32_t video_clips_saved()  { return s_clips; }
uint32_t video_last_millifps(){ return s_millifps; }

bool video_begin() {
  /* init_retry() may call this again after a failure. Release anything a
     partial init left behind, or the retry starts with less heap. */
  esp_camera_deinit();

  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;   c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;   c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;   c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;   c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk  = XCLK_GPIO_NUM;
  c.pin_pclk  = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href  = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn  = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;

  c.xclk_freq_hz = CAM_XCLK_HZ;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = CAM_FRAMESIZE;
  c.jpeg_quality = CAM_JPEG_QUALITY;

  s_have_psram = psramFound();

  if (s_have_psram) {
    /* Framebuffers in PSRAM: room for two, so the sensor can fill N+1 while
       we write N to the card. GRAB_LATEST keeps the queue drained. */
    c.fb_location = CAMERA_FB_IN_PSRAM;
    c.fb_count    = CAM_FB_COUNT;
    c.grab_mode   = CAMERA_GRAB_LATEST;
  } else {
    /* No PSRAM: framebuffers come out of internal DRAM. In JPEG mode the
       driver sizes each one at width*height/5 — 60 KB at VGA — so exactly
       one fits without crowding the SD buffers, audio DMA and task stacks.
       GRAB_LATEST is meaningless with a single buffer, so use WHEN_EMPTY. */
    Serial.println("[cam] PSRAM disabled — falling back to internal DRAM");
    Serial.println("[cam] expect roughly half the frame rate; capture and SD");
    Serial.println("[cam] write can no longer overlap with one framebuffer.");
    Serial.println("[cam] Tools > PSRAM > \"OPI PSRAM\" to use the onboard 8 MB.");
    c.fb_location = CAMERA_FB_IN_DRAM;
    c.fb_count    = 1;
    c.grab_mode   = CAMERA_GRAB_WHEN_EMPTY;
  }

  /* Step down the resolution rather than dying if the framebuffer will not
     fit. Only reachable in the DRAM case in practice. */
  const framesize_t ladder[] = { CAM_FRAMESIZE, FRAMESIZE_VGA,
                                 FRAMESIZE_QVGA, FRAMESIZE_QQVGA };
  esp_err_t err = ESP_FAIL;

  for (size_t i = 0; i < sizeof(ladder) / sizeof(ladder[0]); i++) {
    if (i > 0 && ladder[i] >= c.frame_size) continue;   /* never step up */
    c.frame_size = ladder[i];

    Serial.printf("[cam] init try: framesize=%d fb_count=%d in %s (heap %u KB)\n",
                  (int)c.frame_size, (int)c.fb_count,
                  s_have_psram ? "PSRAM" : "DRAM",
                  (unsigned)(ESP.getFreeHeap() / 1024));

    err = esp_camera_init(&c);
    if (err == ESP_OK) break;

    Serial.printf("[cam] failed 0x%x (%s)\n", err, esp_err_to_name(err));
    if (err != ESP_ERR_NO_MEM) break;   /* not a memory problem, stop trying */

    /* A failed init still allocated part way. Release it before the next
       attempt, or each retry starts with less heap than the one before. */
    esp_camera_deinit();
  }

  if (err != ESP_OK) {
    Serial.printf("[cam] init failed 0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s && s->id.PID == OV5640_PID) {
    s->set_vflip(s, 1);
  }

  camera_fb_t *probe = esp_camera_fb_get();
  if (probe) {
    Serial.printf("[cam] ready — %ux%u, first frame %u B\n",
                  probe->width, probe->height, (unsigned)probe->len);
    esp_camera_fb_return(probe);
  } else {
    Serial.println("[cam] ready, but first frame grab failed");
  }
  return true;
}

static void video_task(void *) {
  uint32_t clip = sd_session_base();   /* 0 cold, else past existing clips */

  for (;;) {
    /* Absolute deadlines derived from t0 so clip boundaries never drift,
       which is what keeps video/NNNNN.avi aligned with audio/NNNNN.wav. */
    uint32_t seq = clip - sd_session_base();   /* 0-based within this session */
    uint32_t clip_start_ms = s_t0 + seq * CLIP_MS;
    uint32_t clip_end_ms   = clip_start_ms + CLIP_MS;

    while ((int32_t)(millis() - clip_start_ms) < 0) vTaskDelay(1);

    char path[40];
    snprintf(path, sizeof(path), "%s/%05lu.avi", DIR_VIDEO, (unsigned long)clip);

    AviWriter w;
    bool opened = false;
    /* 16 bytes per frame. With PSRAM this is free; without it the table comes
       out of internal DRAM, where 9.6 KB matters and ~10 fps means we will
       never approach 600 frames in a 10 s clip anyway. */
    uint32_t cap = s_have_psram ? VIDEO_MAX_FRAMES : VIDEO_MAX_FRAMES_NO_PSRAM;
    if (sd_lock()) {
      opened = avi_open(&w, path, 0, 0, cap);
      sd_unlock();
    }
    if (!opened) {
      Serial.printf("[vid] open failed %s\n", path);
      clip++;
      continue;
    }

    uint32_t first_frame_ms = 0, last_frame_ms = 0;
    bool dims_set = false;

    while ((int32_t)(millis() - clip_end_ms) < 0) {
      camera_fb_t *fb = esp_camera_fb_get();
      if (!fb) { Serial.println("[vid] fb_get failed"); break; }

      if (fb->format != PIXFORMAT_JPEG) {
        Serial.println("[vid] non-JPEG frame, aborting clip");
        esp_camera_fb_return(fb);
        break;
      }

      /* Real sensor dimensions, taken from the first frame rather than
         assumed from the framesize enum. */
      if (!dims_set) {
        w.width  = fb->width;
        w.height = fb->height;
        dims_set = true;
      }

      uint32_t now = millis();
      if (first_frame_ms == 0) first_frame_ms = now;

      if (sd_lock()) {
        avi_add_frame(&w, fb->buf, fb->len);
        sd_unlock();
      }
      last_frame_ms = now;
      esp_camera_fb_return(fb);

      if (w.frames >= w.idx_cap) {
        Serial.println("[vid] idx table full, closing clip early");
        break;
      }
    }

    /* Span of the captured frames, not the nominal 10 s. If the last frame
       landed at 9.7 s the clip really is 9.7 s long and the header should
       say so, otherwise playback runs slow. One frame interval is added back
       because N frames span N intervals of display time, not N-1. */
    uint32_t span = (w.frames > 1) ? (last_frame_ms - first_frame_ms) : 0;
    uint32_t elapsed = (w.frames > 1)
                         ? span + span / (w.frames - 1)
                         : CLIP_MS;

    uint32_t bytes = 0;
    if (sd_lock(10000)) {
      bytes = avi_close(&w, elapsed);
      sd_unlock();
    } else {
      /* Must not just skip this. avi_close owns both the file handle and the
         idx allocation, and SD.begin() allows only 5 open files by default —
         five silent leaks and every later SD.open() fails for good. */
      Serial.println("[vid] SD lock timeout at close, releasing anyway");
      avi_close(&w, elapsed);
    }

    if (bytes) {
      s_millifps = (uint32_t)((uint64_t)w.frames * 1000000ULL / elapsed);
      s_clips++;
      sd_log_event("video", clip, clip_start_ms - s_t0, bytes, w.frames, s_millifps);
      Serial.printf("[vid] %s  %lu frames  %lu B  %lu.%03lu fps\n",
                    path, (unsigned long)w.frames, (unsigned long)bytes,
                    (unsigned long)(s_millifps / 1000),
                    (unsigned long)(s_millifps % 1000));
    }
    clip++;
  }
}

bool video_start_task(uint32_t t0_ms) {
  s_t0 = t0_ms;
  return xTaskCreatePinnedToCore(video_task, "vid", 8192, nullptr, 4, nullptr, 1) == pdPASS;
}
