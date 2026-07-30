#pragma once
#include <Arduino.h>
#include <FS.h>
#include <SD.h>

/* Minimal RIFF/AVI muxer for a single MJPEG video stream.
 *
 * Writes a real container: hdrl (avih + strl/strh/strf) -> movi -> idx1.
 * Frame rate is not known until the clip ends, so the header fields that
 * depend on it are written as placeholders and patched by avi_close().
 *
 * Caller is responsible for holding the SD mutex around open/frame/close.
 */

struct AviWriter {
  File      f;
  uint32_t  frames;
  uint32_t  movi_bytes;      /* payload after the 'movi' fourcc */
  uint32_t  max_chunk;       /* largest JPEG seen, for dwSuggestedBufferSize */
  uint16_t  width, height;
  uint32_t *idx;             /* 4 words per frame: ckid, flags, offset, size */
  uint32_t  idx_cap;
  bool      ok;
};

bool avi_open(AviWriter *w, const char *path, uint16_t width, uint16_t height,
              uint32_t max_frames);

/* Appends one JPEG as a '00dc' chunk. Returns false if the index table is
   full or the write short-changed us. */
bool avi_add_frame(AviWriter *w, const uint8_t *jpeg, size_t len);

/* Writes idx1, patches every size/rate field, closes the file.
   elapsed_ms is the true wall-clock span of the captured frames.
   Returns total file size, or 0 on failure. */
uint32_t avi_close(AviWriter *w, uint32_t elapsed_ms);
