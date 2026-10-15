#include "CommonRadioPrefs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

bool CommonRadioPrefs::getByKey(const char* key, char* value, size_t max_len) {
  if (strcmp(key, "fem_rxgain") == 0) {
    snprintf(value, max_len, "%d", (uint32_t)getFEMRxGain());
    return true;
  }
  if (strcmp(key, "fem_txgain") == 0) {
    snprintf(value, max_len, "%d", (uint32_t)getFEMTxGain());
    return true;
  }
  return false;
}
bool CommonRadioPrefs::setByKey(const char* key, const char* value) {
  if (strcmp(key, "fem_rxgain") == 0) {
    setFEMRxGain(atoi(value));
    markDirty();
    return true;
  }
  if (strcmp(key, "fem_txgain") == 0) {
    setFEMTxGain(atoi(value));
    markDirty();
    return true;
  }
  return false;
}
