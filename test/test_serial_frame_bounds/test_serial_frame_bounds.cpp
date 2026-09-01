#include <gtest/gtest.h>

#include <deque>
#include <vector>

#include "helpers/ArduinoSerialInterface.h"
#include "helpers/ethernet/SerialEthernetInterface.h"

namespace {

std::vector<uint8_t> framed(const std::vector<uint8_t>& payload) {
  std::vector<uint8_t> result;
  result.reserve(payload.size() + 3);
  result.push_back('<');
  result.push_back(static_cast<uint8_t>(payload.size() & 0xFF));
  result.push_back(static_cast<uint8_t>((payload.size() >> 8) & 0xFF));
  result.insert(result.end(), payload.begin(), payload.end());
  return result;
}

class InputStream : public Stream {
public:
  void append(const std::vector<uint8_t>& bytes) {
    _bytes.insert(_bytes.end(), bytes.begin(), bytes.end());
  }

  int available() override { return static_cast<int>(_bytes.size()); }
  int read() override {
    if (_bytes.empty()) return -1;
    const uint8_t value = _bytes.front();
    _bytes.pop_front();
    return value;
  }

private:
  std::deque<uint8_t> _bytes;
};

class EthernetInput : public SerialEthernetInterface {
public:
  void append(const std::vector<uint8_t>& bytes) {
    _bytes.insert(_bytes.end(), bytes.begin(), bytes.end());
  }

  bool isConnected() const override { return true; }
  bool isReadBusy() const override { return !_bytes.empty(); }
  int available() override { return static_cast<int>(_bytes.size()); }
  int read() override {
    if (_bytes.empty()) return -1;
    const uint8_t value = _bytes.front();
    _bytes.pop_front();
    return value;
  }
  size_t write(const uint8_t*, size_t size) override { return size; }

private:
  std::deque<uint8_t> _bytes;
};

std::vector<uint8_t> oversizedResetPrefix() {
  std::vector<uint8_t> payload(MAX_FRAME_SIZE + 1, 0xA5);
  payload[0] = 51;  // CMD_FACTORY_RESET
  payload[1] = 'r';
  payload[2] = 'e';
  payload[3] = 's';
  payload[4] = 'e';
  payload[5] = 't';
  return payload;
}

TEST(SerialFrameBounds, ArduinoDropsOversizedFrameInsteadOfReturningPrefix) {
  InputStream stream;
  stream.append(framed(oversizedResetPrefix()));
  stream.append(framed({22, 1}));

  ArduinoSerialInterface serial;
  serial.begin(stream);
  serial.enable();

  uint8_t output[MAX_FRAME_SIZE];
  memset(output, 0xCC, sizeof(output));
  EXPECT_EQ(0U, serial.checkRecvFrame(output));
  EXPECT_EQ(0xCC, output[0]);
  ASSERT_EQ(2U, serial.checkRecvFrame(output));
  EXPECT_EQ(22, output[0]);
  EXPECT_EQ(1, output[1]);
}

#if ETHERNET_RAW_LINE
TEST(SerialFrameBounds, EthernetRawLineDiscardsOverflowUntilDelimiter) {
  EthernetInput serial;
  serial.enable();

  const std::vector<uint8_t> oversized = oversizedResetPrefix();
  serial.append(std::vector<uint8_t>(oversized.begin(), oversized.end() - 1));

  uint8_t output[MAX_FRAME_SIZE];
  memset(output, 0xCC, sizeof(output));
  EXPECT_EQ(0U, serial.checkRecvFrame(output));
  EXPECT_EQ(0xCC, output[0]);

  serial.append({oversized.back(), 0xA5, '\r', 22, 1, '\n'});
  EXPECT_EQ(0U, serial.checkRecvFrame(output));
  EXPECT_EQ(0xCC, output[0]);
  ASSERT_EQ(2U, serial.checkRecvFrame(output));
  EXPECT_EQ(22, output[0]);
  EXPECT_EQ(1, output[1]);
}
#else
TEST(SerialFrameBounds, EthernetDropsOversizedFrameInsteadOfReturningPrefix) {
  EthernetInput serial;
  serial.enable();
  serial.append(framed(oversizedResetPrefix()));
  serial.append(framed({22, 1}));

  uint8_t output[MAX_FRAME_SIZE];
  memset(output, 0xCC, sizeof(output));
  EXPECT_EQ(0U, serial.checkRecvFrame(output));
  EXPECT_EQ(0xCC, output[0]);
  ASSERT_EQ(2U, serial.checkRecvFrame(output));
  EXPECT_EQ(22, output[0]);
  EXPECT_EQ(1, output[1]);
}
#endif

}  // namespace

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
