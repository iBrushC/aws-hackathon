#pragma once
#include <Arduino.h>

#define WAV_HEADER_BYTES 44

/* Fills a canonical 44-byte PCM WAV header. data_bytes may be 0 when the
   header is first written and patched after the clip is done. */
void wav_header(uint8_t *out, uint32_t data_bytes,
                uint32_t sample_rate, uint16_t channels, uint16_t bits);
