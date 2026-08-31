#include <gtest/gtest.h>

#include <cstring>
#include <string>

#include "../../examples/companion_radio/CompanionUiLogic.h"

namespace {

const smartui::MentionPolicy release_policy = {true, 3, true, true, 3};
const smartui::MentionPolicy strict_policy = {true, 3, false, false, 3};

bool mentions(const char* text, const char* name,
              const smartui::MentionPolicy& policy = release_policy) {
  return smartui::textMentionsNodeName(text, name, policy,
      [](const char*, bool, uint16_t) { return true; });
}

} // namespace

TEST(CompanionMentions, UnicodeMetricsAndCaseFoldingArePreserved) {
  const auto metrics = smartui::mentionNameMetrics("Ёжик Москва");
  EXPECT_EQ(11U, metrics.name_chars);
  EXPECT_EQ(4U, metrics.first_token_chars);
  EXPECT_TRUE(mentions("Привет, @ёжик москва!", "Ёжик Москва"));
  EXPECT_TRUE(mentions("@ЇЖАК!", "їжак"));
  EXPECT_TRUE(mentions("@NODE!", "Node"));
}

TEST(CompanionMentions, FullNameAndFirstTokenKeepTheirExistingRanks) {
  const auto metrics = smartui::mentionNameMetrics("Alice Base");
  EXPECT_EQ(21U, smartui::mentionMatchRankAt("Alice Base!", "Alice Base", true, metrics));
  EXPECT_EQ(10U, smartui::mentionMatchRankAt("Alice!", "Alice Base", true, metrics));
  EXPECT_EQ(0U, smartui::mentionMatchRankAt("Alice!", "Alice Base", false, metrics));
  EXPECT_EQ(0U, smartui::mentionMatchRankAt("Alicex!", "Alice Base", true, metrics));
}

TEST(CompanionMentions, WordBoundariesDoNotBecomeSubstringMatches) {
  EXPECT_FALSE(mentions("Malice and Alicex", "Alice"));
  EXPECT_FALSE(mentions("@Alice_extra", "Alice", strict_policy));
  EXPECT_FALSE(mentions("@Alice-extra", "Alice", strict_policy));
  EXPECT_TRUE(mentions("(@Alice), hi!", "Alice", strict_policy));
}

TEST(CompanionMentions, ReleaseAndStrictPoliciesPreservePlainNameRules) {
  EXPECT_TRUE(mentions("Alice says hi", "Alice Base"));
  EXPECT_TRUE(mentions("Alice Base says hi", "Alice Base"));
  EXPECT_FALSE(mentions("Alice Base says hi", "Alice Base", strict_policy));
  EXPECT_TRUE(mentions("@Alice says hi", "Alice Base", strict_policy));
  EXPECT_FALSE(mentions("Al says hi", "Al Base"));
  EXPECT_TRUE(mentions("@Al says hi", "Al Base", strict_policy));
}

TEST(CompanionMentions, NullEmptyAndSingleCharacterNamesNeverReachOwnershipCheck) {
  int checks = 0;
  auto check = [&](const char*, bool, uint16_t) { ++checks; return true; };
  EXPECT_FALSE(smartui::textMentionsNodeName(nullptr, "Alice", release_policy, check));
  EXPECT_FALSE(smartui::textMentionsNodeName("@Alice", nullptr, release_policy, check));
  EXPECT_FALSE(smartui::textMentionsNodeName("@Alice", "", release_policy, check));
  EXPECT_FALSE(smartui::textMentionsNodeName("@Я", "Я", release_policy, check));
  EXPECT_EQ(0, checks);
}

TEST(CompanionMentions, NonmatchingMessageDoesNotLoadRecentTable) {
  smartui::LazyMentionSnapshot<const char*, 4> recent;
  int loads = 0;
  EXPECT_FALSE(smartui::textMentionsNodeName("Nothing addressed to this node", "Alice",
      release_policy, [&](const char*, bool, uint16_t) {
        recent.load([&](const char**, size_t) { ++loads; return 0; });
        return true;
      }));
  EXPECT_EQ(0, loads);
}

TEST(CompanionMentions, RepeatedAmbiguousMatchesLoadRecentTableOnlyOnce) {
  smartui::LazyMentionSnapshot<const char*, 4> recent;
  int loads = 0;
  int checks = 0;
  auto accept = [&](const char* at, bool allow_first_token, uint16_t own_rank) {
    ++checks;
    const int count = recent.load([&](const char** entries, size_t capacity) {
      ++loads;
      EXPECT_EQ(4U, capacity);
      entries[0] = "Alice Long";
      return 1;
    });
    for (int i = 0; i < count; ++i) {
      if (smartui::mentionMatchRankAt(at, recent.entries[i], allow_first_token) > own_rank) {
        return false;
      }
    }
    return true;
  };
  EXPECT_FALSE(smartui::textMentionsNodeName("@Alice Long @Alice Long @Alice Long", "Alice",
      release_policy, accept));
  EXPECT_GT(checks, 1);
  EXPECT_EQ(1, loads);
}

TEST(CompanionMentions, AnUnambiguousLaterMentionStillSucceeds) {
  int checks = 0;
  EXPECT_TRUE(smartui::textMentionsNodeName("@Alice Long, then @Alice!", "Alice", release_policy,
      [&](const char* at, bool first, uint16_t own_rank) {
        ++checks;
        return smartui::mentionMatchRankAt(at, "Alice Long", first) <= own_rank;
      }));
  EXPECT_GT(checks, 1);
}

TEST(CompanionMentions, EmptyRecentSnapshotIsAlsoCached) {
  smartui::LazyMentionSnapshot<int, 2> recent;
  int loads = 0;
  auto load = [&](int*, size_t) { ++loads; return 0; };
  EXPECT_EQ(0, recent.load(load));
  EXPECT_EQ(0, recent.load(load));
  EXPECT_EQ(1, loads);
}

TEST(CompanionMentions, SenderPrefixIsNotPartOfMentionBody) {
  EXPECT_STREQ("hello", smartui::channelMentionBodyText("Alice: hello"));
  EXPECT_FALSE(mentions(smartui::channelMentionBodyText("Alice: hello"), "Alice"));
  EXPECT_TRUE(mentions(smartui::channelMentionBodyText("Bob: @Alice"), "Alice"));
}

TEST(CompanionCustomVars, ExistingGpsWireFormatIsUnchanged) {
  char payload[176];
  smartui::CustomVarsWriter vars(payload, sizeof(payload));
  ASSERT_TRUE(vars.append("gps", "1"));
  EXPECT_STREQ("gps:1", payload);
  EXPECT_EQ(5U, vars.size());
}

TEST(CompanionCustomVars, PhoneExtensionKeepsOrderSeparatorsAndStatuses) {
  for (const char* state : {"WAIT", "FRESH", "STALE"}) {
    char payload[176];
    smartui::CustomVarsWriter vars(payload, sizeof(payload));
    ASSERT_TRUE(vars.append("gps_source", "PHONE"));
    ASSERT_TRUE(vars.append("phone_gps", state));
    ASSERT_TRUE(vars.append("gps", "0"));
    EXPECT_EQ(std::string("gps_source:PHONE,phone_gps:") + state + ",gps:0", payload);
  }
  char payload[176];
  smartui::CustomVarsWriter vars(payload, sizeof(payload));
  ASSERT_TRUE(vars.append("gps_source", "HW"));
  ASSERT_TRUE(vars.append("phone_gps", "OFF"));
  EXPECT_STREQ("gps_source:HW,phone_gps:OFF", payload);
}

TEST(CompanionCustomVars, ExactFrameLimitLeavesNulAndCanariesIntact) {
  unsigned char storage[179];
  memset(storage, 0xA5, sizeof(storage));
  smartui::CustomVarsWriter vars(reinterpret_cast<char*>(&storage[1]), 176);
  ASSERT_TRUE(vars.append("k", std::string(173, 'x').c_str()));
  EXPECT_EQ(175U, vars.size());
  EXPECT_EQ(0, storage[176]);
  EXPECT_EQ(0xA5, storage[0]);
  EXPECT_EQ(0xA5, storage[177]);
  EXPECT_FALSE(vars.append("a", "b"));
  EXPECT_EQ(175U, vars.size());
}

TEST(CompanionCustomVars, OversizedFieldIsRejectedWithoutPartialCommaOrData) {
  char payload[12];
  smartui::CustomVarsWriter vars(payload, sizeof(payload));
  ASSERT_TRUE(vars.append("gps", "1"));
  EXPECT_FALSE(vars.append("long_key", "value"));
  EXPECT_STREQ("gps:1", payload);
  EXPECT_EQ(5U, vars.size());
  EXPECT_FALSE(vars.append("a", std::string(176, 'x').c_str()));
  EXPECT_STREQ("gps:1", payload);
}

TEST(CompanionCustomVars, EmptySmallAndNullInputsAreSafe) {
  char payload[1] = {'x'};
  smartui::CustomVarsWriter vars(payload, sizeof(payload));
  EXPECT_EQ(0U, vars.size());
  EXPECT_STREQ("", payload);
  EXPECT_FALSE(vars.append("gps", "1"));
  EXPECT_FALSE(vars.append(nullptr, "1"));
  smartui::CustomVarsWriter zero(nullptr, 0);
  EXPECT_FALSE(zero.append("gps", "1"));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
