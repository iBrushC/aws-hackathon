#pragma once
#include <Arduino.h>

/* =========================================================================
 *  TARGET: Seeed XIAO ESP32S3 Sense (OV2640 or OV5640 + PDM mic + SPI microSD)
 *
 *  Camera pins come from the board package's camera_pins.h via this define,
 *  so there is no hand-maintained pin map here. Do not remove it.
 * ========================================================================= */
#define CAMERA_MODEL_XIAO_ESP32S3

/* =========================================================================
 *  CLIP CADENCE
 *  Every clip is CLIP_MS long, back to back, no gap. video/00000.avi is
 *  paired with audio/00000.wav and both start at the same epoch boundary.
 * ========================================================================= */
#define CLIP_MS                10000UL

/* Set to 0 for video only (no mic init, no /audio folder, no WAVs). */
#define CAPTURE_AUDIO          1

/* =========================================================================
 *  VIDEO
 *
 *  FRAMESIZE_VGA = 640x480. The OV2640 will do FRAMESIZE_HD (1280x720) if you
 *  want it, but SPI SD write bandwidth becomes the ceiling and you land around
 *  8-10 fps instead of 20-25.
 *
 *  VIDEO_MAX_FRAMES sizes the in-RAM idx1 table (16 bytes/frame). It is a
 *  ceiling, not a target: 600 frames over a 10 s clip = 60 fps headroom.
 * ========================================================================= */
#define CAM_FRAMESIZE          FRAMESIZE_VGA
#define CAM_JPEG_QUALITY       12       /* 10 best/biggest .. 63 worst/smallest */
#define CAM_XCLK_HZ            20000000
#define CAM_FB_COUNT           2
#define VIDEO_MAX_FRAMES       600

/* =========================================================================
 *  AUDIO — onboard PDM microphone
 *  XIAO ESP32S3 Sense: PDM clock on GPIO42, PDM data on GPIO41.
 * ========================================================================= */
#define AUDIO_SAMPLE_RATE      16000UL
#define AUDIO_BITS             16
#define AUDIO_CHANNELS         1
#define AUDIO_GAIN_SHIFT       2        /* <<n per sample. PDM mics are quiet. 0 = raw. */
#define AUDIO_CHUNK_BYTES      8192     /* I2S read / SD write granularity (~256 ms) */
#define AUDIO_DMA_DESC_NUM     8        /* 8 * 1024 frames ~= 0.5 s of DMA cushion */
#define AUDIO_DMA_FRAME_NUM    1024
#define MIC_PIN_CLK            42
#define MIC_PIN_DATA           41

/* =========================================================================
 *  STORAGE
 *  microSD on the Sense expansion board is SPI, CS on GPIO21.
 *  Card must be <=32 GB and formatted FAT32.
 * ========================================================================= */
#define SD_PIN_CS              21
#define SD_SPI_HZ              20000000
#define WIPE_SD_ON_BOOT        1
#define DIR_VIDEO              "/video"
#define DIR_AUDIO              "/audio"
#define FILE_INDEX             "/index.csv"
