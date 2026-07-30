#pragma once
#include <Arduino.h>
#include <FS.h>
#include <SD.h>

/* Mounts the card, optionally wipes it, creates /video (+ /audio) and
   the CSV header. Must be called before any task starts. */
bool sd_begin();

/* Every filesystem touch from either task goes through these. Two tasks
   share one FAT volume; concurrent open/write/close will corrupt it. */
bool sd_lock(uint32_t timeout_ms = 5000);
void sd_unlock();

/* Appends one row to /index.csv. Takes the lock itself — do not hold it. */
void sd_log_event(const char *kind, uint32_t index, uint32_t rel_ms,
                  uint32_t bytes, uint32_t frames, uint32_t millifps);

uint64_t sd_free_bytes();

/* First clip index for this session. 0 on a cold boot; after a self-restart,
   one past the highest clip already on the card, so nothing is overwritten. */
uint32_t sd_session_base();
