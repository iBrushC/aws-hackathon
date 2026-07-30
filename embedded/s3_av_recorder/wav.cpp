#include "wav.h"

static inline void p32(uint8_t *p, uint32_t v) {
  p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
static inline void p16(uint8_t *p, uint16_t v) {
  p[0] = v; p[1] = v >> 8;
}

void wav_header(uint8_t *h, uint32_t data_bytes,
                uint32_t sample_rate, uint16_t channels, uint16_t bits) {
  const uint16_t align     = channels * (bits / 8);
  const uint32_t byte_rate = sample_rate * align;

  memcpy(h + 0, "RIFF", 4);
  p32   (h + 4, 36 + data_bytes);
  memcpy(h + 8, "WAVE", 4);

  memcpy(h + 12, "fmt ", 4);
  p32   (h + 16, 16);          /* PCM fmt chunk size */
  p16   (h + 20, 1);           /* WAVE_FORMAT_PCM */
  p16   (h + 22, channels);
  p32   (h + 24, sample_rate);
  p32   (h + 28, byte_rate);
  p16   (h + 32, align);
  p16   (h + 34, bits);

  memcpy(h + 36, "data", 4);
  p32   (h + 40, data_bytes);
}
