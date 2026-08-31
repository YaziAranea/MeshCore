#pragma once

#include <Arduino.h>
#include <Mesh.h>
#include "AbstractUITask.h"

/*------------ Frame Protocol --------------*/
#define FIRMWARE_VER_CODE 13

#ifndef FIRMWARE_BUILD_DATE
#define FIRMWARE_BUILD_DATE "14 Aug 2026"
#endif

#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "v1.17.1"
#endif

#ifndef UI_PHONE_GPS
#define UI_PHONE_GPS 0
#endif

#if defined(NRF52_PLATFORM) || defined(STM32_PLATFORM)
#include <InternalFileSystem.h>
#elif defined(RP2040_PLATFORM)
#include <LittleFS.h>
#elif defined(ESP32)
#include <SPIFFS.h>
#endif

#include "DataStore.h"
#include "NodePrefs.h"

#include <RTClib.h>
#include <helpers/ArduinoHelpers.h>
#include <helpers/BaseSerialInterface.h>
#if __has_include(<helpers/BoardLedControl.h>)
  #include <helpers/BoardLedControl.h>
#else
  // Allows this data-layer commit to compile before the display/runtime helper
  // commit is applied.  The real helper replaces these no-op fallbacks.
  inline bool meshcoreBoardLedsEnabled() { return true; }
  inline void meshcoreSetBoardLedsEnabled(bool) { }
#endif
#include <helpers/IdentityStore.h>
#include <helpers/SimpleMeshTables.h>
#include <helpers/StaticPoolPacketManager.h>
#include <target.h>

/* ---------------------------------- CONFIGURATION ------------------------------------- */

#ifndef LORA_FREQ
#define LORA_FREQ 915.0
#endif
#ifndef LORA_BW
#define LORA_BW 250
#endif
#ifndef LORA_SF
#define LORA_SF 10
#endif
#ifndef LORA_CR
#define LORA_CR 5
#endif
#ifndef LORA_TX_POWER
#define LORA_TX_POWER 20
#endif
#ifndef MAX_LORA_TX_POWER
#define MAX_LORA_TX_POWER LORA_TX_POWER
#endif

#ifndef PHONE_GPS_STALE_MS
#define PHONE_GPS_STALE_MS 300000UL
#endif

#ifndef MAX_CONTACTS
#define MAX_CONTACTS 100
#endif

#ifndef OFFLINE_QUEUE_SIZE
#define OFFLINE_QUEUE_SIZE 16
#endif

#ifndef BLE_NAME_PREFIX
#define BLE_NAME_PREFIX "MeshCore-"
#endif

#include <helpers/BaseChatMesh.h>
#include <helpers/TransportKeyStore.h>

/* -------------------------------------------------------------------------------------- */

#define REQ_TYPE_GET_STATUS             0x01 // same as _GET_STATS
#define REQ_TYPE_KEEP_ALIVE             0x02
#define REQ_TYPE_GET_TELEMETRY_DATA     0x03

struct AdvertPath {
  uint8_t pubkey_prefix[7];
  uint8_t path_len;
  char    name[32];
  uint32_t recv_timestamp;
  uint8_t path[MAX_PATH_SIZE];
};

#ifndef NETWORK_STATUS_TABLE_SIZE
#define NETWORK_STATUS_TABLE_SIZE 16
#endif

#ifndef NETWORK_STATUS_MAX_AGE_SECS
#define NETWORK_STATUS_MAX_AGE_SECS (15 * 60)
#endif

#define NETWORK_STATUS_REPEATER              0x01
#define NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN 0x02
#define NETWORK_STATUS_CHANNEL_TRAFFIC       0x04
#define NETWORK_STATUS_VIA_RELAY             0x08
#define NETWORK_STATUS_DIRECT                0x10

struct NetworkStatusEntry {
  uint8_t pubkey_prefix[7];
  char name[32];
  uint32_t recv_timestamp;
  int8_t snr_q4;
  int8_t rssi;
  uint8_t type;
  uint8_t flags;
  uint8_t path_len;
};

#ifndef RECENT_CHAT_TABLE_SIZE
  #if (defined(HELTEC_T114_WITH_DISPLAY) && defined(ST7789)) || defined(HELTEC_LORA_V4_TFT) || defined(HELTEC_LORA_V4_3_OLED)
    #define RECENT_CHAT_TABLE_SIZE 20
  #else
    #define RECENT_CHAT_TABLE_SIZE 12
  #endif
#endif

struct RecentChatEntry {
  uint32_t recv_timestamp;
  uint8_t path_len;
  uint8_t flags;
  int8_t snr_q4;
  int8_t rssi;
  char origin[32];
  char text[160];
};

struct LinkTestStatus {
  bool active;
  bool done;
  bool has_target;
  char target[32];
  uint8_t sent;
  uint8_t ok;
  uint8_t failed;
  uint8_t total;
  uint16_t last_rtt_ms;
  uint16_t avg_rtt_ms;
  uint16_t timeout_ms;
  int8_t last_snr_q4;
  int8_t best_snr_q4;
  int8_t worst_snr_q4;
  int8_t last_rssi;
  uint8_t sent_direct;
};

class MyMesh : public BaseChatMesh, public DataStoreHost {
public:
  MyMesh(mesh::Radio &radio, mesh::RNG &rng, mesh::RTCClock &rtc, SimpleMeshTables &tables, DataStore& store, AbstractUITask* ui=NULL);

  void begin(bool has_display);
  void startInterface(BaseSerialInterface &serial);

  const char *getNodeName();
  NodePrefs *getNodePrefs();
  uint32_t getBLEPin();

  void loop();
  void handleCmdFrame(size_t len);
  bool advert();
  uint16_t getAutoAdvertIntervalMins() const;
  void cycleAutoAdvertInterval();
  void applyUiPrefsRuntime();
  bool isPhoneGpsEnabled() const {
#if UI_PHONE_GPS == 1
    return _prefs.gps_source == GPS_SOURCE_PHONE;
#else
    return false;
#endif
  }
  bool isPhoneGpsFresh() const;
  uint32_t getPhoneGpsAgeSeconds() const;
  const char* getGpsSourceName() const;
  void setGpsSource(uint8_t source, bool save = true);
  bool setPhoneGpsFix(int32_t lat, int32_t lon, int32_t alt = 0);
  bool getShareableLocation(double& lat, double& lon, double& alt) const;
  bool sendQuickReply(const char* text);
  int getQuickReplyChannelCount();
  int getQuickReplyContactCount();
  bool getQuickReplyChannel(uint16_t list_idx, uint8_t& channel_idx, ChannelDetails& channel);
  bool getQuickReplyContact(uint16_t list_idx, ContactInfo& contact);
  bool sendQuickReplyToChannel(uint16_t list_idx, const char* text);
  bool sendQuickReplyToContact(uint16_t list_idx, const char* text);
  void enterCLIRescue();

  int  getRecentlyHeard(AdvertPath dest[], int max_num);
  int  getRecentNetworkStatus(NetworkStatusEntry dest[], int max_num,
                              uint32_t max_age_secs = NETWORK_STATUS_MAX_AGE_SECS);
  int  getRecentChannelMessages(RecentChatEntry dest[], int max_num);
  bool startLinkTest();
  void getLinkTestStatus(LinkTestStatus& dest) const;
  unsigned long getChannelBusyTime() const { return channel_busy_ms; }

protected:
  float getAirtimeBudgetFactor() const override;
  int getInterferenceThreshold() const override;
  bool getCADEnabled() const override;
  int calcRxDelay(float score, uint32_t air_time) const override;
  uint32_t getRetransmitDelay(const mesh::Packet *packet) override;
  uint32_t getDirectRetransmitDelay(const mesh::Packet *packet) override;
  uint8_t getExtraAckTransmitCount() const override;
  bool filterRecvFloodPacket(mesh::Packet* packet) override;
  bool allowPacketForward(const mesh::Packet* packet) override;

  void sendFloodScoped(const TransportKey& scope, mesh::Packet* pkt, uint32_t delay_millis);
  void sendFloodScoped(const ContactInfo& recipient, mesh::Packet* pkt, uint32_t delay_millis=0) override;
  void sendFloodScoped(const mesh::GroupChannel& channel, mesh::Packet* pkt, uint32_t delay_millis=0) override;

  void logRxRaw(float snr, float rssi, const uint8_t raw[], int len) override;
  bool isAutoAddEnabled() const override;
  bool shouldAutoAddContactType(uint8_t type) const override;
  bool shouldOverwriteWhenFull() const override;
  uint8_t getAutoAddMaxHops() const override;
  void onContactsFull() override;
  void onContactOverwrite(const uint8_t* pub_key) override;
  bool onContactPathRecv(ContactInfo& from, uint8_t* in_path, uint8_t in_path_len, uint8_t* out_path, uint8_t out_path_len, uint8_t extra_type, uint8_t* extra, uint8_t extra_len) override;
  void onDiscoveredContact(ContactInfo &contact, bool is_new, uint8_t path_len, const uint8_t* path) override;
  void onContactPathUpdated(const ContactInfo &contact) override;
  ContactInfo* processAck(const uint8_t *data) override;
  void queueMessage(const ContactInfo &from, uint8_t txt_type, mesh::Packet *pkt, uint32_t sender_timestamp,
                    const uint8_t *extra, int extra_len, const char *text);

  void onMessageRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                     const char *text) override;
  void onCommandDataRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                         const char *text) override;
  void onSignedMessageRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                           const uint8_t *sender_prefix, const char *text) override;
  void onChannelMessageRecv(const mesh::GroupChannel &channel, mesh::Packet *pkt, uint32_t timestamp,
                            const char *text) override;
  void onChannelDataRecv(const mesh::GroupChannel &channel, mesh::Packet *pkt, uint16_t data_type,
                         const uint8_t *data, size_t data_len) override;

  uint8_t onContactRequest(const ContactInfo &contact, uint32_t sender_timestamp, const uint8_t *data,
                           uint8_t len, uint8_t *reply) override;
  void onContactResponse(const ContactInfo &contact, const uint8_t *data, uint8_t len) override;
  void onControlDataRecv(mesh::Packet *packet) override;
  void onRawDataRecv(mesh::Packet *packet) override;
  void onTraceRecv(mesh::Packet *packet, uint32_t tag, uint32_t auth_code, uint8_t flags,
                   const uint8_t *path_snrs, const uint8_t *path_hashes, uint8_t path_len) override;

  uint32_t calcFloodTimeoutMillisFor(uint32_t pkt_airtime_millis) const override;
  uint32_t calcDirectTimeoutMillisFor(uint32_t pkt_airtime_millis, uint8_t path_len) const override;
  void onSendTimeout() override;

  // DataStoreHost methods
  bool onContactLoaded(const ContactInfo& contact) override { return addContact(contact); }
  bool getContactForSave(uint32_t idx, ContactInfo& contact) override { return getContactByIdx(idx, contact); }
  bool onChannelLoaded(uint8_t channel_idx, const ChannelDetails& ch) override { return setChannel(channel_idx, ch); }
  bool getChannelForSave(uint8_t channel_idx, ChannelDetails& ch) override { return getChannel(channel_idx, ch); }

  void clearPendingReqs() {
    pending_login = pending_status = pending_telemetry = pending_discovery = pending_req = 0;
  }

public:
  void savePrefs() {
    _prefs.node_lat = isPhoneGpsEnabled() ? 0.0 : sensors.node_lat;
    _prefs.node_lon = isPhoneGpsEnabled() ? 0.0 : sensors.node_lon;
    _store->savePrefs(_prefs);
  }

  bool areBoardLedsEnabled() const { return _prefs.board_leds_enabled != 0; }
  void setBoardLedsEnabled(bool enabled) {
    _prefs.board_leds_enabled = enabled ? 1 : 0;
    meshcoreSetBoardLedsEnabled(enabled);
    savePrefs();
  }
  void toggleBoardLeds() { setBoardLedsEnabled(!areBoardLedsEnabled()); }

  bool isClientRepeatEnabled() const { return _prefs.isRepeatEn(); }
  void setClientRepeatEnabled(bool enabled) {
    _prefs.setRepeatEn(enabled);
    savePrefs();
  }
  void toggleClientRepeat() { setClientRepeatEnabled(!isClientRepeatEnabled()); }

  bool isUnreadLedEnabled() const { return _prefs.unread_led_enabled != 0; }
  void setUnreadLedEnabled(bool enabled) {
    _prefs.unread_led_enabled = enabled ? 1 : 0;
    savePrefs();
  }
  void toggleUnreadLed() { setUnreadLedEnabled(!isUnreadLedEnabled()); }

  bool areMsgPopupsEnabled() const { return _prefs.msg_popup_enabled != 0; }
  void setMsgPopupsEnabled(bool enabled) {
    _prefs.msg_popup_enabled = enabled ? 1 : 0;
    savePrefs();
  }
  void toggleMsgPopups() { setMsgPopupsEnabled(!areMsgPopupsEnabled()); }

#if ENV_INCLUDE_GPS == 1
  void applyGpsPrefs() {
    sensors.setSettingValue("gps",
      (_prefs.gps_source == GPS_SOURCE_HW && _prefs.gps_enabled) ? "1" : "0");
    if (_prefs.gps_interval > 0) {
      char interval_str[12];  // Max: 24 hours = 86400 seconds (5 digits + null)
      sprintf(interval_str, "%u", _prefs.gps_interval);
      sensors.setSettingValue("gps_interval", interval_str);
    }
  }
#endif

  // To check if there is pending work
  bool hasPendingWork() const;

private:
  mesh::Packet* createAdvertWithShareableLocation();
  void writeOKFrame();
  void writeErrFrame(uint8_t err_code);
  void writeDisabledFrame();
  void writeContactRespFrame(uint8_t code, const ContactInfo &contact);
  void updateContactFromFrame(ContactInfo &contact, uint32_t& last_mod, const uint8_t *frame, int len);
  void addToOfflineQueue(const uint8_t frame[], int len);
  int getFromOfflineQueue(uint8_t frame[]);
  int getBlobByKey(const uint8_t key[], int key_len, uint8_t dest_buf[]) override { 
    return _store->getBlobByKey(key, key_len, dest_buf);
  }
  bool putBlobByKey(const uint8_t key[], int key_len, const uint8_t src_buf[], int len) override {
    return _store->putBlobByKey(key, key_len, src_buf, len);
  }

  void checkCLIRescueCmd();
  void checkSerialInterface();
  bool isValidClientRepeatFreq(uint32_t f) const;
  uint8_t getRouteStatusFlags(uint8_t path_len) const;
  void noteNetworkStatus(const ContactInfo& contact, uint8_t path_len);
  void noteTrafficStatus(const char* name, uint8_t slot, uint8_t path_len, uint8_t flags);
  void noteChannelChat(const char* channel_name, mesh::Packet* pkt, const char* text);
  void sampleChannelBusy();
  void updateAutoAdvertTimer();

  // helpers, short-cuts
  void saveChannels() { _store->saveChannels(this); }
  void saveContacts();

  DataStore* _store;
  NodePrefs _prefs;
  uint32_t pending_login;
  uint32_t pending_status;
  uint32_t pending_telemetry, pending_discovery;   // pending _TELEMETRY_REQ
  uint32_t pending_req;   // pending _BINARY_REQ
  BaseSerialInterface *_serial;
  AbstractUITask* _ui;

  ContactsIterator _iter;
  uint32_t _iter_filter_since;
  uint32_t _most_recent_lastmod;
  uint32_t _active_ble_pin;
  bool _iter_started;
  bool _cli_rescue;
  bool send_unscoped;   // force un-scoped flood (instead of using send_scope)
  char cli_command[80];
  uint8_t app_target_ver;
  uint8_t *sign_data;
  uint32_t sign_data_len;
  unsigned long dirty_contacts_expiry;

  TransportKey send_scope;

  uint8_t cmd_frame[MAX_FRAME_SIZE + 1];
  uint8_t out_frame[MAX_FRAME_SIZE + 1];
  CayenneLPP telemetry;

  struct Frame {
    uint8_t len;
    uint8_t buf[MAX_FRAME_SIZE];

    bool isChannelMsg() const;
    bool isDisplayableDirectMsg() const;
  };
  int offline_queue_len;
  Frame offline_queue[OFFLINE_QUEUE_SIZE];

  struct AckTableEntry {
    unsigned long msg_sent;
    uint32_t ack;
    ContactInfo* contact;
  };
  #define EXPECTED_ACK_TABLE_SIZE 8
  AckTableEntry expected_ack_table[EXPECTED_ACK_TABLE_SIZE]; // circular table
  int next_ack_idx;

  #define ADVERT_PATH_TABLE_SIZE   16
  AdvertPath advert_paths[ADVERT_PATH_TABLE_SIZE]; // circular table
  NetworkStatusEntry network_status[NETWORK_STATUS_TABLE_SIZE];
  RecentChatEntry recent_chat[RECENT_CHAT_TABLE_SIZE];
  LinkTestStatus link_test;
  int8_t last_rx_snr_q4;
  int8_t last_rx_rssi;
  unsigned long last_rx_millis;
  int recent_chat_head;
  unsigned long channel_busy_ms;
  unsigned long channel_busy_sample_ms;
  unsigned long next_auto_advert;
  unsigned long phone_gps_last_update_ms;
};

extern MyMesh the_mesh;
