#include "audio_capture.h"
#include "config.h"
#include "sd_store.h"
#include "wav.h"

#if CAPTURE_AUDIO

#include <driver/i2s_pdm.h>

static i2s_chan_handle_t s_rx = nullptr;
static uint32_t s_t0 = 0;
static volatile uint32_t s_clips = 0;
static uint8_t *s_buf = nullptr;

static const uint32_t BYTES_PER_FRAME = (AUDIO_BITS / 8) * AUDIO_CHANNELS;
static const uint32_t CLIP_BYTES =
    AUDIO_SAMPLE_RATE * BYTES_PER_FRAME * (CLIP_MS / 1000UL);

uint32_t audio_clips_saved() { return s_clips; }

/* PDM mics sit on a large DC offset. Left alone it eats headroom and makes
   AUDIO_GAIN_SHIFT clip far earlier than the numbers suggest. */
static void condition(uint8_t *buf, size_t bytes) {
  int16_t *s = (int16_t *)buf;
  size_t n = bytes / 2;
  static int32_t dc = 0;
  for (size_t i = 0; i < n; i++) {
    dc += ((int32_t)s[i] - dc) >> 10;          /* slow high-pass */
    int32_t v = ((int32_t)s[i] - dc) << AUDIO_GAIN_SHIFT;
    if (v >  32767) v =  32767;
    if (v < -32768) v = -32768;
    s[i] = (int16_t)v;
  }
}

bool audio_begin() {
  s_buf = (uint8_t *)malloc(AUDIO_CHUNK_BYTES);
  if (!s_buf) return false;

  i2s_chan_config_t ch = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  ch.dma_desc_num  = AUDIO_DMA_DESC_NUM;
  ch.dma_frame_num = AUDIO_DMA_FRAME_NUM;
  ch.auto_clear    = true;
  if (i2s_new_channel(&ch, nullptr, &s_rx) != ESP_OK) return false;

  i2s_pdm_rx_config_t pdm = {
    .clk_cfg  = I2S_PDM_RX_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
    .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,
                                               I2S_SLOT_MODE_MONO),
    .gpio_cfg = {
      .clk = (gpio_num_t)MIC_PIN_CLK,
      .din = (gpio_num_t)MIC_PIN_DATA,
      .invert_flags = { .clk_inv = false },
    },
  };
  if (i2s_channel_init_pdm_rx_mode(s_rx, &pdm) != ESP_OK) return false;
  if (i2s_channel_enable(s_rx) != ESP_OK) return false;

  Serial.println("[mic] ready");
  return true;
}

static void audio_task(void *) {
  uint32_t clip = 0;
  uint8_t header[WAV_HEADER_BYTES];

  for (;;) {
    char path[40];
    snprintf(path, sizeof(path), "%s/%05lu.wav", DIR_AUDIO, (unsigned long)clip);

    uint32_t rel_ms = millis() - s_t0;

    File f;
    if (sd_lock()) {
      f = SD.open(path, FILE_WRITE);
      if (f) {
        wav_header(header, 0, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_BITS);
        f.write(header, WAV_HEADER_BYTES);
      }
      sd_unlock();
    }
    if (!f) { Serial.printf("[mic] open failed %s\n", path); clip++; continue; }

    /* Driven by sample count, not millis(). Each WAV is then exactly CLIP_MS
       of audio no matter how long an SD write stalled. */
    uint32_t written = 0;
    while (written < CLIP_BYTES) {
      size_t want = CLIP_BYTES - written;
      if (want > AUDIO_CHUNK_BYTES) want = AUDIO_CHUNK_BYTES;

      size_t got = 0;
      esp_err_t err = i2s_channel_read(s_rx, s_buf, want, &got, pdMS_TO_TICKS(1000));
      if (err != ESP_OK || got == 0) {
        Serial.printf("[mic] read err 0x%x\n", err);
        continue;
      }
      condition(s_buf, got);

      if (sd_lock()) {
        f.write(s_buf, got);
        sd_unlock();
      }
      written += got;
    }

    if (sd_lock()) {
      wav_header(header, written, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_BITS);
      f.seek(0);
      f.write(header, WAV_HEADER_BYTES);
      f.close();
      sd_unlock();
    }

    s_clips++;
    sd_log_event("audio", clip, rel_ms, written + WAV_HEADER_BYTES, 0, 0);
    Serial.printf("[mic] %s  %lu B\n", path, (unsigned long)written);
    clip++;
  }
}

bool audio_start_task(uint32_t t0_ms) {
  s_t0 = t0_ms;
  return xTaskCreatePinnedToCore(audio_task, "mic", 4096, nullptr, 5, nullptr, 0) == pdPASS;
}

#else  /* CAPTURE_AUDIO == 0 */

bool audio_begin() { return true; }
bool audio_start_task(uint32_t) { return true; }
uint32_t audio_clips_saved() { return 0; }

#endif
