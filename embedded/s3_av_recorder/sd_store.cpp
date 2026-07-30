#include "sd_store.h"
#include "config.h"
#include <SPI.h>

static SemaphoreHandle_t s_mtx = nullptr;

bool sd_lock(uint32_t timeout_ms) {
  if (!s_mtx) return false;
  return xSemaphoreTake(s_mtx, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void sd_unlock() {
  if (s_mtx) xSemaphoreGive(s_mtx);
}

static void rm_rf(const char *path) {
  File dir = SD.open(path);
  if (!dir || !dir.isDirectory()) { if (dir) dir.close(); return; }

  /* Collect names first. Deleting while the directory handle is walking it
     is undefined behaviour on the ESP32 FAT layer. */
  String names[64];
  int n = 0;
  for (File e = dir.openNextFile(); e && n < 64; e = dir.openNextFile()) {
    names[n++] = String(e.path());
    e.close();
  }
  dir.close();

  for (int i = 0; i < n; i++) SD.remove(names[i].c_str());
  if (n == 64) rm_rf(path);   /* directory had more than one batch */
}

bool sd_begin() {
  s_mtx = xSemaphoreCreateMutex();
  if (!s_mtx) return false;

  if (!SD.begin(SD_PIN_CS, SPI, SD_SPI_HZ)) {
    Serial.println("[sd] mount failed");
    return false;
  }
  if (SD.cardType() == CARD_NONE) {
    Serial.println("[sd] no card");
    return false;
  }
  Serial.printf("[sd] mounted, %llu MB total\n", SD.cardSize() / (1024ULL * 1024ULL));

#if WIPE_SD_ON_BOOT
  Serial.println("[sd] wiping");
  rm_rf(DIR_VIDEO);
  rm_rf(DIR_AUDIO);
  SD.rmdir(DIR_VIDEO);
  SD.rmdir(DIR_AUDIO);
  SD.remove(FILE_INDEX);
#endif

  SD.mkdir(DIR_VIDEO);
#if CAPTURE_AUDIO
  SD.mkdir(DIR_AUDIO);
#endif

  if (!SD.exists(FILE_INDEX)) {
    File f = SD.open(FILE_INDEX, FILE_WRITE);
    if (f) {
      f.println("kind,index,rel_ms,bytes,frames,millifps");
      f.close();
    }
  }
  return true;
}

void sd_log_event(const char *kind, uint32_t index, uint32_t rel_ms,
                  uint32_t bytes, uint32_t frames, uint32_t millifps) {
  if (!sd_lock()) return;
  File f = SD.open(FILE_INDEX, FILE_APPEND);
  if (f) {
    f.printf("%s,%lu,%lu,%lu,%lu,%lu\n", kind,
             (unsigned long)index, (unsigned long)rel_ms,
             (unsigned long)bytes, (unsigned long)frames,
             (unsigned long)millifps);
    f.close();
  }
  sd_unlock();
}

uint64_t sd_free_bytes() {
  return SD.totalBytes() - SD.usedBytes();
}
