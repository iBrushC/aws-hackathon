#pragma once
#include <Arduino.h>

bool audio_begin();
bool audio_start_task(uint32_t t0_ms);
uint32_t audio_clips_saved();
