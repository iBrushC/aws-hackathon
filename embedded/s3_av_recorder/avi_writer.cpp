#include "avi_writer.h"

/* ---------------------------------------------------------------------------
 * Fixed header layout. Everything up to and including the 'movi' fourcc is a
 * constant 224 bytes, which is what lets us seek back and patch by offset.
 *
 *   0   'RIFF'                          |  108  strh body (56 B)
 *   4   riff size            [PATCH]    |  164  'strf'
 *   8   'AVI '                          |  168  40
 *  12   'LIST'                          |  172  BITMAPINFOHEADER (40 B)
 *  16   192  (hdrl payload)             |  212  'LIST'
 *  20   'hdrl'                          |  216  movi size        [PATCH]
 *  24   'avih'                          |  220  'movi'
 *  28   56                              |  224  first frame chunk
 *  32   avih body (56 B)                |
 *  88   'LIST'                          |
 *  92   116  (strl payload)             |
 *  96   'strl'                          |
 * 100   'strh'                          |
 * 104   56                              |
 * ------------------------------------------------------------------------- */
#define OFF_RIFF_SIZE     4
#define OFF_AVIH          32
#define OFF_STRH          108
#define OFF_BIH           172
#define OFF_MOVI_SIZE     216
#define OFF_MOVI_FOURCC   220
#define HEADER_BYTES      224

static inline void put32(uint8_t *p, uint32_t v) {
  p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
static inline void put16(uint8_t *p, uint16_t v) {
  p[0] = v; p[1] = v >> 8;
}
static inline void put4cc(uint8_t *p, const char *s) {
  p[0] = s[0]; p[1] = s[1]; p[2] = s[2]; p[3] = s[3];
}

/* Seek to abs offset, overwrite one little-endian u32, leave position dirty. */
static bool patch32(File &f, uint32_t offset, uint32_t value) {
  uint8_t b[4];
  put32(b, value);
  if (!f.seek(offset)) return false;
  return f.write(b, 4) == 4;
}

static bool patch16(File &f, uint32_t offset, uint16_t value) {
  uint8_t b[2];
  put16(b, value);
  if (!f.seek(offset)) return false;
  return f.write(b, 2) == 2;
}

bool avi_open(AviWriter *w, const char *path, uint16_t width, uint16_t height,
              uint32_t max_frames) {
  /* Explicit field reset, NOT memset — see the note in avi_writer.h. */
  w->frames     = 0;
  w->movi_bytes = 0;
  w->max_chunk  = 0;
  w->ok         = false;
  w->width      = width;
  w->height     = height;

  /* 16 bytes per frame. Lives in PSRAM so it never competes with the
     internal DRAM that WiFi/camera want. */
  w->idx_cap = max_frames;
  w->idx = (uint32_t *)ps_malloc((size_t)max_frames * 16);
  if (!w->idx) w->idx = (uint32_t *)malloc((size_t)max_frames * 16);
  if (!w->idx) { Serial.println("[avi] idx alloc failed"); return false; }

  w->f = SD.open(path, FILE_WRITE);
  if (!w->f) {
    Serial.printf("[avi] cannot open %s\n", path);
    free(w->idx); w->idx = nullptr;
    return false;
  }

  uint8_t h[HEADER_BYTES];
  memset(h, 0, sizeof(h));

  put4cc(h + 0,  "RIFF");
  put32 (h + 4,  0);                 /* PATCH: filesize - 8 */
  put4cc(h + 8,  "AVI ");

  put4cc(h + 12, "LIST");
  put32 (h + 16, 192);               /* hdrl payload: 4 + 64 + 124 */
  put4cc(h + 20, "hdrl");

  /* ---- avih (MainAVIHeader) ---- */
  put4cc(h + 24, "avih");
  put32 (h + 28, 56);
  put32 (h + OFF_AVIH +  0, 0);      /* PATCH dwMicroSecPerFrame */
  put32 (h + OFF_AVIH +  4, 0);      /* PATCH dwMaxBytesPerSec */
  put32 (h + OFF_AVIH +  8, 0);      /* dwPaddingGranularity */
  put32 (h + OFF_AVIH + 12, 0x10);   /* dwFlags = AVIF_HASINDEX */
  put32 (h + OFF_AVIH + 16, 0);      /* PATCH dwTotalFrames */
  put32 (h + OFF_AVIH + 20, 0);      /* dwInitialFrames */
  put32 (h + OFF_AVIH + 24, 1);      /* dwStreams */
  put32 (h + OFF_AVIH + 28, 0);      /* PATCH dwSuggestedBufferSize */
  put32 (h + OFF_AVIH + 32, width);
  put32 (h + OFF_AVIH + 36, height);
  /* +40..+55 dwReserved[4] already zero */

  /* ---- strl ---- */
  put4cc(h + 88, "LIST");
  put32 (h + 92, 116);               /* strl payload: 4 + 64 + 48 */
  put4cc(h + 96, "strl");

  /* ---- strh (AVIStreamHeader) ---- */
  put4cc(h + 100, "strh");
  put32 (h + 104, 56);
  put4cc(h + OFF_STRH +  0, "vids");
  put4cc(h + OFF_STRH +  4, "MJPG");
  put32 (h + OFF_STRH +  8, 0);      /* dwFlags */
  put16 (h + OFF_STRH + 12, 0);      /* wPriority */
  put16 (h + OFF_STRH + 14, 0);      /* wLanguage */
  put32 (h + OFF_STRH + 16, 0);      /* dwInitialFrames */
  put32 (h + OFF_STRH + 20, 1);      /* PATCH dwScale */
  put32 (h + OFF_STRH + 24, 1);      /* PATCH dwRate  -> fps = rate/scale */
  put32 (h + OFF_STRH + 28, 0);      /* dwStart */
  put32 (h + OFF_STRH + 32, 0);      /* PATCH dwLength = frame count */
  put32 (h + OFF_STRH + 36, 0);      /* PATCH dwSuggestedBufferSize */
  put32 (h + OFF_STRH + 40, 0xFFFFFFFF); /* dwQuality = default */
  put32 (h + OFF_STRH + 44, 0);      /* dwSampleSize = 0 for video */
  put16 (h + OFF_STRH + 48, 0);      /* rcFrame.left */
  put16 (h + OFF_STRH + 50, 0);      /* rcFrame.top */
  put16 (h + OFF_STRH + 52, width);  /* rcFrame.right */
  put16 (h + OFF_STRH + 54, height); /* rcFrame.bottom */

  /* ---- strf (BITMAPINFOHEADER) ---- */
  put4cc(h + 164, "strf");
  put32 (h + 168, 40);
  put32 (h + OFF_BIH +  0, 40);      /* biSize */
  put32 (h + OFF_BIH +  4, width);
  put32 (h + OFF_BIH +  8, height);
  put16 (h + OFF_BIH + 12, 1);       /* biPlanes */
  put16 (h + OFF_BIH + 14, 24);      /* biBitCount */
  put4cc(h + OFF_BIH + 16, "MJPG");  /* biCompression */
  put32 (h + OFF_BIH + 20, (uint32_t)width * height * 3); /* biSizeImage */
  /* remaining fields zero */

  /* ---- movi ---- */
  put4cc(h + 212, "LIST");
  put32 (h + 216, 0);                /* PATCH: 4 + movi_bytes */
  put4cc(h + 220, "movi");

  if (w->f.write(h, HEADER_BYTES) != HEADER_BYTES) {
    Serial.println("[avi] header write failed");
    w->f.close();
    free(w->idx); w->idx = nullptr;
    return false;
  }

  w->ok = true;
  return true;
}

bool avi_add_frame(AviWriter *w, const uint8_t *jpeg, size_t len) {
  if (!w->ok || w->frames >= w->idx_cap) return false;

  uint8_t ch[8];
  put4cc(ch + 0, "00dc");
  put32 (ch + 4, (uint32_t)len);

  /* Offset recorded in idx1 is relative to the 'movi' fourcc itself, so the
     first frame lands at 4. This is the convention every player expects. */
  uint32_t rel_offset = 4 + w->movi_bytes;

  if (w->f.write(ch, 8) != 8) { w->ok = false; return false; }
  if (w->f.write(jpeg, len) != (int)len) { w->ok = false; return false; }

  uint32_t pad = len & 1;            /* RIFF chunks are word aligned */
  if (pad) { uint8_t z = 0; w->f.write(&z, 1); }

  uint32_t *e = w->idx + w->frames * 4;
  memcpy(e, "00dc", 4);
  e[1] = 0x10;                       /* AVIIF_KEYFRAME — every MJPEG frame is */
  e[2] = rel_offset;
  e[3] = (uint32_t)len;

  w->movi_bytes += 8 + len + pad;
  if (len > w->max_chunk) w->max_chunk = (uint32_t)len;
  w->frames++;
  return true;
}

uint32_t avi_close(AviWriter *w, uint32_t elapsed_ms) {
  if (!w->f) { if (w->idx) { free(w->idx); w->idx = nullptr; } return 0; }

  uint32_t total = 0;

  if (w->frames == 0 || elapsed_ms == 0) {
    Serial.println("[avi] no frames captured, discarding");
    w->f.close();
    free(w->idx); w->idx = nullptr;
    return 0;
  }

  /* ---- idx1 ---- */
  uint8_t ih[8];
  put4cc(ih + 0, "idx1");
  put32 (ih + 4, w->frames * 16);
  w->f.write(ih, 8);
  w->f.write((const uint8_t *)w->idx, w->frames * 16);

  uint32_t filesize = HEADER_BYTES + w->movi_bytes + 8 + w->frames * 16;

  /* ---- the whole point: real timing, measured, not assumed ----
     fps = rate / scale. Using scale = elapsed_ms and rate = frames * 1000
     gives the exact ratio with no rounding at all. */
  uint32_t scale = elapsed_ms;
  uint32_t rate  = w->frames * 1000UL;
  uint32_t usec_per_frame = (uint32_t)((uint64_t)elapsed_ms * 1000ULL / w->frames);
  uint32_t bytes_per_sec  = (uint32_t)((uint64_t)w->movi_bytes * 1000ULL / elapsed_ms);

  patch32(w->f, OFF_RIFF_SIZE,        filesize - 8);
  patch32(w->f, OFF_AVIH +  0,        usec_per_frame);
  patch32(w->f, OFF_AVIH +  4,        bytes_per_sec);
  patch32(w->f, OFF_AVIH + 16,        w->frames);
  patch32(w->f, OFF_AVIH + 28,        w->max_chunk);
  patch32(w->f, OFF_STRH + 20,        scale);
  patch32(w->f, OFF_STRH + 24,        rate);
  patch32(w->f, OFF_STRH + 32,        w->frames);
  patch32(w->f, OFF_STRH + 36,        w->max_chunk);
  patch32(w->f, OFF_MOVI_SIZE,        4 + w->movi_bytes);

  /* Dimensions are not known until the first frame arrives, so they were
     written as zeros by avi_open and have to be patched here too. All three
     header structures carry them independently and players disagree about
     which one they trust, so all three must agree. */
  patch32(w->f, OFF_AVIH + 32,        w->width);
  patch32(w->f, OFF_AVIH + 36,        w->height);
  patch16(w->f, OFF_STRH + 52,        w->width);   /* rcFrame.right  */
  patch16(w->f, OFF_STRH + 54,        w->height);  /* rcFrame.bottom */
  patch32(w->f, OFF_BIH  +  4,        w->width);   /* biWidth  */
  patch32(w->f, OFF_BIH  +  8,        w->height);  /* biHeight */
  patch32(w->f, OFF_BIH  + 20,        (uint32_t)w->width * w->height * 3);

  w->f.flush();
  w->f.close();
  free(w->idx);
  w->idx = nullptr;
  total = filesize;
  return total;
}
