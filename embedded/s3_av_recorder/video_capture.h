#pragma once
#include <Arduino.h>

/* Initialises the OV2640/OV5640 in JPEG mode at CAM_FRAMESIZE. */
bool video_begin();

/* Starts the recorder task. Writes back-to-back CLIP_MS clips to
   /video/00000.avi, /video/00001.avi, ... aligned to t0_ms. */
bool video_start_task(uint32_t t0_ms);

uint32_t video_clips_saved();
uint32_t video_last_millifps();   /* fps * 1000, for the health log */
