#pragma once
#include <cstdint> // For uint8_t, uint32_t
#include <helpers/ConfigSerializer.h>
#include <helpers/SmartUiQuickReplies.h>
#include <helpers/CommonRadioPrefs.h>
#include <helpers/DynamicConfigSerializer.h>

#define TELEM_MODE_DENY            0
#define TELEM_MODE_ALLOW_FLAGS     1     // use contact.flags
#define TELEM_MODE_ALLOW_ALL       2

#define ADVERT_LOC_NONE       0
#define ADVERT_LOC_SHARE      1

#define GPS_SOURCE_HW         0
#define GPS_SOURCE_PHONE      1

#define NOTIFY_MODE_SILENT    0x00
#define NOTIFY_MODE_GPIO      0x01
#define NOTIFY_MODE_TONE      0x02
#define NOTIFY_MODE_VIBE      0x04
#define NOTIFY_MODE_ALL       (NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE | NOTIFY_MODE_VIBE)

#define NOTIFY_TONE_COUNT     31
#define DEFAULT_NOTIFY_TONE_RESONANCE_HZ 3000

#define SMART_PROFILE_CUSTOM   0
#define SMART_PROFILE_QUIET    1
#define SMART_PROFILE_OUTDOOR  2
#define SMART_PROFILE_NIGHT    3

#define SMART_FAVORITE_NOTIFY_MODE       1
#define SMART_FAVORITE_IMPORTANT_NOTIFY  2
#define SMART_FAVORITE_SYSTEM_TONE       3
#define SMART_FAVORITE_DM_TONE           4
#define SMART_FAVORITE_MENTION_TONE      5
#define SMART_FAVORITE_UI_FONT           6
#define SMART_FAVORITE_UI_THEME          7
#define SMART_FAVORITE_BLUETOOTH         8
#define SMART_FAVORITE_AUTO_ADVERT       9
#define SMART_FAVORITE_GPS              10
#define SMART_FAVORITE_BOARD_LEDS       11
#define SMART_FAVORITE_LOW_BATTERY      12
#define SMART_FAVORITE_ADC              13
#define SMART_FAVORITE_PROFILE          14
#define SMART_FAVORITE_MAX              SMART_FAVORITE_PROFILE

#define CH2_MODE_OFF          0
#define CH2_MODE_RELAY        1
#define CH2_MODE_LISTEN       2
#define CH2_MODE_BATCH        3

class NodePrefs : public ConfigSerializer {  // persisted to file
public:
  float airtime_factor = 0;
  char node_name[32];
  double node_lat = 0, node_lon = 0;
  float freq = 0;
  uint8_t sf = 0;
  uint8_t cr = 0;
  uint8_t multi_acks = 0;
  uint8_t manual_add_contacts = 0;
  float bw = 0;
  int8_t tx_power_dbm = 0;
  uint8_t telemetry_mode_base = 0;
  uint8_t telemetry_mode_loc = 0;
  uint8_t telemetry_mode_env = 0;
  float rx_delay_base = 0;
  float tx_delay_factor = 0;
  float direct_tx_delay_factor = 0;
  uint32_t ble_pin = 0;
  uint8_t  advert_loc_policy = 0;
  uint8_t  buzzer_quiet = 0;
  uint8_t  vibe_quiet = 0;
  uint8_t  gps_enabled = 0;      // GPS enabled flag (0=disabled, 1=enabled)
  uint32_t gps_interval = 0;     // GPS read interval in seconds
  uint8_t autoadd_config = 0;    // bitmask for auto-add contacts config
  uint8_t rx_boosted_gain = 0; // SX126x RX boosted gain mode (0=power saving, 1=boosted)
  uint8_t radio_fem_rxgain = 0; // external LoRa FEM RX gain (LNA)
  uint8_t radio_fem_txgain = 0; // external LoRa FEM TX gain (low by default)
  uint8_t _client_repeat = 0;  // DEPRECATED -> use repeat.disable_fwd
  uint8_t path_hash_mode = 0;    // which path mode to use when sending
  uint8_t autoadd_max_hops = 0;  // 0 = no limit, 1 = direct (0 hops), N = up to N-1 hops (max 64)
  uint8_t cad_enabled = 0;
  uint8_t interference_threshold = 0;
  uint8_t agc_reset_interval = 0;  // secs / 4
  char default_scope_name[31];
  uint8_t default_scope_key[16];
  float adc_multiplier = 0;      // 0 = use the board ADC multiplier
  uint8_t notify_mode = 0;       // NOTIFY_MODE_* bitmask
  int8_t notify_gpio_pin = -1;
  int8_t notify_tone_pin = -1;
  uint8_t notify_tone_id = 0;
  uint8_t notify_tone_volume = 10;
  uint16_t auto_advert_interval_mins = 0;
  uint8_t ch2_mode = CH2_MODE_OFF;
  uint8_t board_leds_enabled = 1;
  uint8_t ui_font = 0;
  uint8_t ui_theme = 0;
  uint8_t unread_led_enabled = 1;
  uint8_t msg_popup_enabled = 1;
  uint8_t important_notify_mode = 0;
  uint8_t notifications_muted = 0;
  uint8_t ui_top_color = 1;
  uint8_t ui_bottom_color = 0;
  uint8_t backlight_timeout_idx = 0;
  int8_t notify_vibe_pin = -1;
  uint8_t offline_dm_led_enabled = 1;
  uint8_t ble_dm_led_enabled = 1;
  uint8_t low_battery_shutdown_enabled = 1;
  uint8_t notify_tone_bridge_enabled = 0;
  uint8_t notify_tone_8bit_enabled = 0;
  uint8_t notify_tone_high_drive_enabled = 0;
  uint8_t notify_pin_fix_version = 0;
  uint16_t notify_tone_resonance_hz = DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
  uint8_t notify_tone_dm_id = 0;
  uint8_t notify_tone_mention_id = 0;
  uint8_t notify_tone_system_id = 0;
  uint8_t smart_profile_id = SMART_PROFILE_CUSTOM;
  uint8_t favorite_setting_1 = SMART_FAVORITE_NOTIFY_MODE;
  uint8_t favorite_setting_2 = SMART_FAVORITE_SYSTEM_TONE;
  uint8_t favorite_setting_3 = SMART_FAVORITE_BLUETOOTH;
  uint32_t night_prompt_day = 0;
  uint8_t night_quiet_active = 0;
  uint8_t gps_source = GPS_SOURCE_HW;
  int16_t timezone_offset_minutes = 360;  // UTC+06:00 compatibility default
  uint8_t powersaving_enabled = 1; // Companion power-saving policy; not a new user preference.
  uint8_t agc_reset_enabled = 0; // Optional periodic SX126x AGC reset; existing devices stay OFF.
  char quick_replies[SMARTUI_QUICK_REPLY_COUNT][SMARTUI_QUICK_REPLY_MAX_BYTES + 1] = {};
  int8_t tz_offset = 0;
#ifdef ENABLE_WIFI_INTERFACE
  #ifndef WIFI_SSID
    #define WIFI_SSID ""
  #endif
  char wifi_ssid[33] = {0};   // if empty, the compile-time WIFI_SSID is used
  char wifi_pwd[64] = {0};
  uint8_t wifi_enabled = 1; // enabled by default to allow wifi only builds to work. wifi won't be started if ssid is empty
  // use ssid from prefs, or fallback to ssid from build flags
  const char* getWifiSSID() const { return wifi_ssid[0] ? wifi_ssid : WIFI_SSID; }
#endif

private:
  class RadioPrefs : public CommonRadioPrefs {
    NodePrefs* _parent;
  protected:
    void structure() override {
      def("freq", _parent->freq);
      def("bw", _parent->bw);
      def("sf", _parent->sf);
      def("cr", _parent->cr);
      def("cad", _parent->cad_enabled);
      def("int_thr", _parent->interference_threshold);
      def("rxgain", _parent->rx_boosted_gain);
      // Existing upstream radio keys. Missing keys in an older prefs.json keep
      // board defaults; once changed, both FEM controls survive a reboot.
      def("fem_rxgain", _parent->radio_fem_rxgain);
      def("fem_txgain", _parent->radio_fem_txgain);
      def("tx", _parent->tx_power_dbm);
      def("af", _parent->airtime_factor);
      def("rxdelay", _parent->rx_delay_base);
      def("f_txdelay", _parent->tx_delay_factor);
      def("d_txdelay", _parent->direct_tx_delay_factor);
      def("agc_int", _parent->agc_reset_interval);
      def("hash_mode", _parent->path_hash_mode);
      def("multi_ack", _parent->multi_acks);
    }
  public:
    RadioPrefs(NodePrefs* parent) : _parent(parent) { }

    // CommonRadioPrefs interface
    float getFreq() const override { return _parent->freq; }
    void setFreq(float f) override { _parent->freq = f; markDirty(); }
    float getBandwidth() const override { return _parent->bw; }
    void setBandwidth(float bw) override { _parent->bw = bw; markDirty(); }
    uint8_t getSpreadFactor() const override { return _parent->sf; }
    void setSpreadFactor(uint8_t sf) override { _parent->sf = sf; markDirty(); }
    uint8_t getCodingRate() const override { return _parent->cr; }
    void setCodingRate(uint8_t cr) override { _parent->cr = cr; markDirty(); }
    float getAirtimeFactor() const override { return _parent->airtime_factor; }
    void setAirtimeFactor(float af) override { _parent->airtime_factor = af; markDirty(); }
    bool isCadEnabled() const override { return _parent->cad_enabled; }
    void setCadEnabled(bool en) override { _parent->cad_enabled = en; markDirty(); }
    uint8_t getIntThresh() const override { return _parent->interference_threshold; }
    void setIntThresh(uint8_t t) override { _parent->interference_threshold = t; markDirty(); }
    uint8_t getRxGain() const override { return _parent->rx_boosted_gain; }
    void setRxGain(uint8_t g) override { _parent->rx_boosted_gain = g; markDirty(); }
    int8_t getTxPower() const override { return _parent->tx_power_dbm; }
    void setTxPower(int8_t dbm) override { _parent->tx_power_dbm = dbm; markDirty(); }
    float getRxDelay() const override { return _parent->rx_delay_base; }
    void setRxDelay(float d) override { _parent->rx_delay_base = d; markDirty(); }
    uint16_t getAgcResetInt() const override { return _parent->agc_reset_interval * 4; }
    void setAgcResetInt(uint16_t secs) override { _parent->agc_reset_interval = secs / 4; markDirty(); }
    uint8_t getHashMode() const override { return _parent->path_hash_mode; }
    void setHashMode(uint8_t m) override { _parent->path_hash_mode = m; markDirty(); }
    uint8_t getMultiAcks() const override { return _parent->multi_acks; }
    void setMultiAcks(uint8_t m) override { _parent->multi_acks = m; markDirty(); }
    float getFloodTxDelay() const override { return _parent->tx_delay_factor; }
    void setFloodTxDelay(float d) override { _parent->tx_delay_factor = d; markDirty(); }
    float getDirectTxDelay() const override { return _parent->direct_tx_delay_factor; }
    void setDirectTxDelay(float d) override { _parent->direct_tx_delay_factor = d; markDirty(); }
    uint8_t getFEMRxGain() const override { return _parent->radio_fem_rxgain; }
    void setFEMRxGain(uint8_t g) override { _parent->radio_fem_rxgain = g; markDirty(); }
    uint8_t getFEMTxGain() const override { return _parent->radio_fem_txgain; }
    void setFEMTxGain(uint8_t g) override { _parent->radio_fem_txgain = g; markDirty(); }
  };
  RadioPrefs radio;

  class GPSPrefs : public ConfigSerializer {  // COPIED from CommonCLI (for now)
    NodePrefs* _parent;
  protected:
    void structure() override {
      def("en", _parent->gps_enabled); // boolean
      def("int", _parent->gps_interval);   // interval in seconds
      def("adv_loc", _parent->advert_loc_policy);
    }
  public:
    GPSPrefs(NodePrefs* parent) : _parent(parent) { }
  };
  GPSPrefs gps;

  class RepeatPrefs : public ConfigSerializer {  // COPIED from CommonCLI (for now)
  public:
    uint8_t disable_fwd = 1;
  protected:
    void structure() override {
      def("disable", disable_fwd);
      //def("f_max", flood_max);
      //def("f_max_uns", flood_max_unscoped);
      //def("f_max_adv", flood_max_advert);
      //def("loop", loop_detect);
    }
  };
  RepeatPrefs repeat;

  class CompanionPrefs : public ConfigSerializer {
    NodePrefs* _parent;
  protected:
    void structure() override {
      def("auto_max", _parent->autoadd_max_hops);  // 0 = no limit, 1 = direct (0 hops), N = up to N-1 hops (max 64)
      def("defs_nm", _parent->default_scope_name, sizeof(_parent->default_scope_name));
      def("defs_key", (void *) _parent->default_scope_key, sizeof(_parent->default_scope_key));
      def("pin", _parent->ble_pin);
      def("buzz_q", _parent->buzzer_quiet);
      def("vibe_q", _parent->vibe_quiet);
      def("auto_add", _parent->autoadd_config);    // bitmask for auto-add contacts config
      def("man_add", _parent->manual_add_contacts);
      def("tel_base", _parent->telemetry_mode_base);
      def("tel_loc", _parent->telemetry_mode_loc);
      def("tel_env", _parent->telemetry_mode_env);
      def("tz_offset", _parent->tz_offset);
    }
  public:
    CompanionPrefs(NodePrefs* parent) : _parent(parent) { }
  };
  CompanionPrefs companion;

  class SmartUIPrefs : public ConfigSerializer {
    NodePrefs* _parent;
  protected:
    void structure() override {
      // Keep keys below CONFIG_MAX_KEYLEN and stable: they are part of the
      // on-device prefs.json format.
      def("adc", _parent->adc_multiplier);
      def("notify", _parent->notify_mode);
      def("gpio", _parent->notify_gpio_pin);
      def("tone_pin", _parent->notify_tone_pin);
      def("tone", _parent->notify_tone_id);
      def("volume", _parent->notify_tone_volume);
      def("advert_min", _parent->auto_advert_interval_mins);
      def("ch2", _parent->ch2_mode);
      def("leds", _parent->board_leds_enabled);
      def("font", _parent->ui_font);
      def("theme", _parent->ui_theme);
      def("unread_led", _parent->unread_led_enabled);
      def("popup", _parent->msg_popup_enabled);
      def("important", _parent->important_notify_mode);
      def("muted", _parent->notifications_muted);
      def("top", _parent->ui_top_color);
      def("bottom", _parent->ui_bottom_color);
      def("bl_timeout", _parent->backlight_timeout_idx);
      def("vibe_pin", _parent->notify_vibe_pin);
      def("offline_led", _parent->offline_dm_led_enabled);
      def("ble_led", _parent->ble_dm_led_enabled);
      def("low_batt", _parent->low_battery_shutdown_enabled);
      def("bridge", _parent->notify_tone_bridge_enabled);
      def("tone_8bit", _parent->notify_tone_8bit_enabled);
      def("high_drive", _parent->notify_tone_high_drive_enabled);
      def("pin_fix", _parent->notify_pin_fix_version);
      def("res_hz", _parent->notify_tone_resonance_hz);
      def("tone_dm", _parent->notify_tone_dm_id);
      def("tone_mention", _parent->notify_tone_mention_id);
      def("tone_system", _parent->notify_tone_system_id);
      def("profile", _parent->smart_profile_id);
      def("favorite_1", _parent->favorite_setting_1);
      def("favorite_2", _parent->favorite_setting_2);
      def("favorite_3", _parent->favorite_setting_3);
      def("night_day", _parent->night_prompt_day);
      def("night_quiet", _parent->night_quiet_active);
      def("gps_source", _parent->gps_source);
      def("tz_min", _parent->timezone_offset_minutes);
      def("agc_reset", _parent->agc_reset_enabled);
      for (uint8_t slot = 0; slot < SMARTUI_QUICK_REPLY_COUNT; ++slot) {
        char key[] = "reply_1";
        key[6] = static_cast<char>('1' + slot);
        def(key, _parent->quick_replies[slot], sizeof(_parent->quick_replies[slot]));
      }
    }
  public:
    SmartUIPrefs(NodePrefs* parent) : _parent(parent) { }
  };
  SmartUIPrefs smart_ui;

  void copyValuesFrom(const NodePrefs& other) {
    airtime_factor = other.airtime_factor;
    memcpy(node_name, other.node_name, sizeof(node_name));
    node_lat = other.node_lat;
    node_lon = other.node_lon;
    freq = other.freq;
    sf = other.sf;
    cr = other.cr;
    multi_acks = other.multi_acks;
    manual_add_contacts = other.manual_add_contacts;
    bw = other.bw;
    tx_power_dbm = other.tx_power_dbm;
    telemetry_mode_base = other.telemetry_mode_base;
    telemetry_mode_loc = other.telemetry_mode_loc;
    telemetry_mode_env = other.telemetry_mode_env;
    rx_delay_base = other.rx_delay_base;
    tx_delay_factor = other.tx_delay_factor;
    direct_tx_delay_factor = other.direct_tx_delay_factor;
    cad_enabled = other.cad_enabled;
    interference_threshold = other.interference_threshold;
    agc_reset_interval = other.agc_reset_interval;
    tz_offset = other.tz_offset;
#ifdef ENABLE_WIFI_INTERFACE
    memcpy(wifi_ssid, other.wifi_ssid, sizeof(wifi_ssid));
    memcpy(wifi_pwd, other.wifi_pwd, sizeof(wifi_pwd));
    wifi_enabled = other.wifi_enabled;
#endif
    ble_pin = other.ble_pin;
    advert_loc_policy = other.advert_loc_policy;
    buzzer_quiet = other.buzzer_quiet;
    vibe_quiet = other.vibe_quiet;
    gps_enabled = other.gps_enabled;
    gps_interval = other.gps_interval;
    autoadd_config = other.autoadd_config;
    rx_boosted_gain = other.rx_boosted_gain;
    radio_fem_rxgain = other.radio_fem_rxgain;
    radio_fem_txgain = other.radio_fem_txgain;
    _client_repeat = other._client_repeat;
    path_hash_mode = other.path_hash_mode;
    autoadd_max_hops = other.autoadd_max_hops;
    memcpy(default_scope_name, other.default_scope_name, sizeof(default_scope_name));
    memcpy(default_scope_key, other.default_scope_key, sizeof(default_scope_key));
    adc_multiplier = other.adc_multiplier;
    notify_mode = other.notify_mode;
    notify_gpio_pin = other.notify_gpio_pin;
    notify_tone_pin = other.notify_tone_pin;
    notify_tone_id = other.notify_tone_id;
    notify_tone_volume = other.notify_tone_volume;
    auto_advert_interval_mins = other.auto_advert_interval_mins;
    ch2_mode = other.ch2_mode;
    board_leds_enabled = other.board_leds_enabled;
    ui_font = other.ui_font;
    ui_theme = other.ui_theme;
    unread_led_enabled = other.unread_led_enabled;
    msg_popup_enabled = other.msg_popup_enabled;
    important_notify_mode = other.important_notify_mode;
    notifications_muted = other.notifications_muted;
    ui_top_color = other.ui_top_color;
    ui_bottom_color = other.ui_bottom_color;
    backlight_timeout_idx = other.backlight_timeout_idx;
    notify_vibe_pin = other.notify_vibe_pin;
    offline_dm_led_enabled = other.offline_dm_led_enabled;
    ble_dm_led_enabled = other.ble_dm_led_enabled;
    low_battery_shutdown_enabled = other.low_battery_shutdown_enabled;
    notify_tone_bridge_enabled = other.notify_tone_bridge_enabled;
    notify_tone_8bit_enabled = other.notify_tone_8bit_enabled;
    notify_tone_high_drive_enabled = other.notify_tone_high_drive_enabled;
    notify_pin_fix_version = other.notify_pin_fix_version;
    notify_tone_resonance_hz = other.notify_tone_resonance_hz;
    notify_tone_dm_id = other.notify_tone_dm_id;
    notify_tone_mention_id = other.notify_tone_mention_id;
    notify_tone_system_id = other.notify_tone_system_id;
    smart_profile_id = other.smart_profile_id;
    favorite_setting_1 = other.favorite_setting_1;
    favorite_setting_2 = other.favorite_setting_2;
    favorite_setting_3 = other.favorite_setting_3;
    night_prompt_day = other.night_prompt_day;
    night_quiet_active = other.night_quiet_active;
    gps_source = other.gps_source;
    timezone_offset_minutes = other.timezone_offset_minutes;
    agc_reset_enabled = other.agc_reset_enabled;
    memcpy(quick_replies, other.quick_replies, sizeof(quick_replies));
    repeat.disable_fwd = other.repeat.disable_fwd;
    // Serializer objects keep their own parent/fallback pointers. Never copy
    // those pointers from a temporary transaction or loaded prefs generation.
    clearDirty();
    if (other.isDirty()) markDirty();
    custom.copyValuesFrom(other.custom);
  }
  DynamicConfigSerializer custom;

#ifdef ENABLE_WIFI_INTERFACE
  class WiFiPrefs : public ConfigSerializer {
    NodePrefs* _parent;
  protected:
    void structure() override {
      def("ssid", _parent->wifi_ssid, sizeof(_parent->wifi_ssid));
      def("pwd", _parent->wifi_pwd, sizeof(_parent->wifi_pwd));
      def("enabled", _parent->wifi_enabled);
    }
  public:
    WiFiPrefs(NodePrefs* parent) : _parent(parent) { }
  };
  WiFiPrefs wifi;
#endif

protected:
  void structure() override {
    def("name", node_name, sizeof(node_name));
    //def("adv_int", advert_interval);
    //def("f_adv_int", flood_advert_interval);
    def("lat", node_lat);
    def("lon", node_lon);
    def("radio", radio);
    def("gps", gps);
    def("repeat", repeat);
    def("comp", companion);
    def("smart_ui", smart_ui);
    def("custom", custom);
#ifdef ENABLE_WIFI_INTERFACE
    def("wifi", wifi);
#endif
  }
public:
  NodePrefs() : radio(this), gps(this), companion(this), smart_ui(this), custom(&radio)
#ifdef ENABLE_WIFI_INTERFACE
    , wifi(this)
#endif
  {
    node_name[0] = 0;
    default_scope_name[0] = 0;
    memset(default_scope_key, 0, sizeof(default_scope_key));
  }
  NodePrefs(const NodePrefs& other) : NodePrefs() {
    copyValuesFrom(other);
  }
  NodePrefs& operator=(const NodePrefs& other) {
    if (this != &other) copyValuesFrom(other);
    return *this;
  }
  // new accessor methods
  bool isRepeatEn() const { return repeat.disable_fwd == 0; }
  void setRepeatEn(bool en) { repeat.disable_fwd = en ? 0 : 1; }
  void normalizeQuickReplies() {
    for (auto& text : quick_replies) {
      text[SMARTUI_QUICK_REPLY_MAX_BYTES] = 0;
      if (!smartui::validQuickReply(text)) memset(text, 0, sizeof(text));
    }
  }

  CommonRadioPrefs* getRadioPrefs() { return &radio; }
  KeyValueStore* getCustom() { return &custom; }

  bool isDirty() const override {
    return ConfigSerializer::isDirty() || radio.isDirty() || custom.isDirty();
  }
  void clearDirty() override {
    ConfigSerializer::clearDirty(); radio.clearDirty(); custom.clearDirty();
  }
};

inline bool migrateLegacyNotifyPins(NodePrefs& prefs, int8_t alert_pin,
                                    int8_t default_gpio_pin, int8_t default_tone_pin,
                                    uint8_t target_version) {
  if (target_version == 0 || prefs.notify_pin_fix_version >= target_version) return false;

  if (prefs.notify_gpio_pin == alert_pin && default_gpio_pin != alert_pin) {
    prefs.notify_gpio_pin = default_gpio_pin;
  }
  if (prefs.notify_tone_pin == alert_pin && default_tone_pin != alert_pin) {
    prefs.notify_tone_pin = default_tone_pin;
  }
  prefs.notify_pin_fix_version = target_version;
  return true;
}

inline int16_t normalizeTimezoneOffsetMinutes(int32_t value) {
  // The on-device picker uses half-hour steps and the civil-time range
  // UTC-12:00 through UTC+14:00. Invalid persisted data falls back to the
  // historical SmartUI default (Omsk, UTC+06:00) instead of affecting night mode.
  if (value < -720 || value > 840 || value % 30 != 0) return 360;
  return static_cast<int16_t>(value);
}
