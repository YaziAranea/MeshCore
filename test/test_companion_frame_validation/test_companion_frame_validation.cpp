#include <gtest/gtest.h>

#include "../../examples/companion_radio/CompanionFrameValidation.h"
#include "../../examples/companion_radio/ChannelBusyPolicy.h"

namespace {

constexpr size_t kCapacity = 176;
constexpr size_t kPublicKeySize = 32;
constexpr size_t kMaxPathSize = 64;
constexpr size_t kMaxPacketPayload = 184;

companion::FrameValidationResult validate(const uint8_t* frame, size_t length) {
  return companion::validateCommandFrame(frame, length, kCapacity, kPublicKeySize,
                                         kMaxPathSize, kMaxPacketPayload);
}

TEST(CompanionFrameReader, NeverAdvancesPastTheProvidedFrame) {
  const uint8_t bytes[] = {1, 2, 3, 4};
  companion::FrameReader reader(bytes, sizeof(bytes));
  uint8_t value = 0;
  EXPECT_TRUE(reader.readU8(value));
  EXPECT_EQ(1, value);
  uint8_t pair[2] = {};
  EXPECT_TRUE(reader.readBytes(pair, sizeof(pair)));
  EXPECT_EQ(2, pair[0]);
  EXPECT_EQ(3, pair[1]);
  EXPECT_FALSE(reader.readBytes(pair, sizeof(pair)));
  EXPECT_EQ(1U, reader.remaining());
  EXPECT_TRUE(reader.skip(1));
  EXPECT_FALSE(reader.readU8(value));
}

TEST(CompanionFrameReader, TokensAndStringsAreBoundedByTheCurrentFrame) {
  const uint8_t bytes[] = {'x', 'r', 'e', 's', 'e', 't', 'n', 'a', 'm', 'e', 0, 'z'};
  companion::FrameReader reader(bytes, sizeof(bytes));
  EXPECT_TRUE(reader.equalsAt(1, "reset", 5));
  EXPECT_FALSE(reader.equalsAt(8, "reset", 5));
  size_t text_length = 0;
  EXPECT_TRUE(reader.boundedCStringLength(6, 6, text_length));
  EXPECT_EQ(4U, text_length);
  EXPECT_FALSE(reader.boundedCStringLength(6, 4, text_length));
}

TEST(CompanionFrameValidation, ChannelTextNeedsEveryFixedField) {
  uint8_t frame[7] = {companion::kSendChannelTextMessage};
  for (size_t length = 1; length < sizeof(frame); ++length) {
    EXPECT_EQ(companion::kFrameTooShort, validate(frame, length)) << length;
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, sizeof(frame)));
}

TEST(CompanionFrameValidation, ContactUpdateNeedsTheCompleteFixedRecord) {
  uint8_t frame[148] = {};
  frame[0] = companion::kAddUpdateContact;
  frame[35] = 0xFF;  // unknown/flood path is valid for a contact
  for (size_t length = 1; length < 136; ++length) {
    EXPECT_EQ(companion::kFrameTooShort, validate(frame, length)) << length;
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 136));
  for (size_t length = 137; length < 144; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length)) << length;
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 144));
  for (size_t length = 145; length < 148; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length)) << length;
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, sizeof(frame)));

  frame[35] = 0xC0;  // reserved four-byte path-hash encoding
  EXPECT_EQ(companion::kFrameInvalidPath, validate(frame, 136));
}

TEST(CompanionFrameValidation, ChannelDataAccountsForEncodedPathBytes) {
  uint8_t frame[16] = {companion::kSendChannelData, 0, 0x42};
  // 0x42 is two two-byte hashes: four bytes of path plus two-byte data type.
  EXPECT_EQ(companion::kFrameTooShort, validate(frame, 8));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 9));

  frame[2] = 0xFF;  // flood carries no explicit path bytes
  EXPECT_EQ(companion::kFrameTooShort, validate(frame, 4));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 5));

  frame[2] = 0xC0;
  EXPECT_EQ(companion::kFrameInvalidPath, validate(frame, 5));
}

TEST(CompanionFrameValidation, ContactAndSettingsCommandsRejectTruncatedKeysAndFields) {
  const uint8_t commands[] = {
      companion::kRemoveContact, companion::kShareContact,
      companion::kGetContactByKey, companion::kResetPath,
      companion::kSetRadioParams, companion::kSetRadioTxPower,
      companion::kSetTuningParams, companion::kSetOtherParams,
      companion::kSetPathHashMode, companion::kSetAutoaddConfig,
  };
  uint8_t frame[kCapacity] = {};
  for (uint8_t command : commands) {
    frame[0] = command;
    const size_t minimum = companion::minimumCommandFrameLength(
        command, kPublicKeySize, kMaxPathSize);
    ASSERT_GT(minimum, 1U);
    EXPECT_EQ(companion::kFrameTooShort, validate(frame, minimum - 1))
        << static_cast<unsigned>(command);
    EXPECT_EQ(companion::kFrameValid, validate(frame, minimum))
        << static_cast<unsigned>(command);
  }
}

TEST(CompanionFrameValidation, OptionalFixedWidthFieldsCannotBePartial) {
  uint8_t frame[64] = {};
  frame[0] = companion::kGetContacts;
  EXPECT_EQ(companion::kFrameValid, validate(frame, 1));
  for (size_t length = 2; length < 5; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length));
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 5));

  frame[0] = companion::kSetAdvertLatLon;
  EXPECT_EQ(companion::kFrameValid, validate(frame, 9));
  for (size_t length = 10; length < 13; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length));
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 13));

  frame[0] = companion::kExportContact;
  EXPECT_EQ(companion::kFrameValid, validate(frame, 1));
  for (size_t length = 2; length < 1 + kPublicKeySize; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length));
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 1 + kPublicKeySize));
}

TEST(CompanionFrameValidation, DestructiveAndScopeCommandsRequireCompleteShapes) {
  uint8_t frame[64] = {};
  frame[0] = companion::kReboot;
  EXPECT_EQ(companion::kFrameTooShort, validate(frame, 6));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 7));

  frame[0] = companion::kFactoryReset;
  EXPECT_EQ(companion::kFrameTooShort, validate(frame, 5));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 6));

  frame[0] = companion::kSetDefaultFloodScope;
  EXPECT_EQ(companion::kFrameValid, validate(frame, 1));
  for (size_t length = 2; length < 48; ++length) {
    EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, length)) << length;
  }
  EXPECT_EQ(companion::kFrameValid, validate(frame, 48));
}

TEST(CompanionFrameValidation, TelemetryAcceptsOnlyLocalOrCompleteRemoteForm) {
  uint8_t frame[40] = {companion::kSendTelemetryRequest};
  EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, 1));
  EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, 3));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 4));
  EXPECT_EQ(companion::kFrameInvalidShape, validate(frame, 35));
  EXPECT_EQ(companion::kFrameValid, validate(frame, 36));
}

TEST(CompanionFrameValidation, OversizeFramesAreRejectedBeforeParsing) {
  uint8_t frame[kCapacity + 1] = {};
  frame[0] = companion::kGetDeviceTime;
  EXPECT_EQ(companion::kFrameTooLarge, validate(frame, sizeof(frame)));
  EXPECT_EQ(companion::kFrameEmpty, validate(frame, 0));
  EXPECT_EQ(companion::kFrameEmpty, validate(nullptr, 1));
}

TEST(CompanionFrameValidation, EveryCommandAndInRangeLengthHasABoundedResult) {
  uint8_t frame[kCapacity] = {};
  for (unsigned command = 0; command <= 0xFF; ++command) {
    frame[0] = static_cast<uint8_t>(command);
    for (size_t length = 0; length <= sizeof(frame); ++length) {
      const companion::FrameValidationResult result = validate(frame, length);
      EXPECT_GE(result, companion::kFrameValid);
      EXPECT_LE(result, companion::kFrameInvalidShape);
      EXPECT_NE(companion::kFrameTooLarge, result);
    }
  }
}

TEST(ChannelBusyPolicy, PollsOnlyAtTheConfiguredWrapSafeInterval) {
  EXPECT_FALSE(companion::channelBusySampleDue(1099, 1000, 100));
  EXPECT_TRUE(companion::channelBusySampleDue(1100, 1000, 100));
  EXPECT_TRUE(companion::channelBusySampleDue(0x00000054U, 0xFFFFFFF0U, 100));
}

TEST(ChannelBusyPolicy, AccountsShortSamplesButNotSleepSizedGaps) {
  EXPECT_EQ(100U, companion::channelBusyElapsedToAccount(1100, 1000, 100, true));
  EXPECT_EQ(0U, companion::channelBusyElapsedToAccount(1100, 1000, 100, false));
  EXPECT_EQ(0U, companion::channelBusyElapsedToAccount(1300, 1000, 100, true));
  EXPECT_EQ(100U, companion::channelBusyElapsedToAccount(
                      0x00000054U, 0xFFFFFFF0U, 100, true));
}

}  // namespace

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
