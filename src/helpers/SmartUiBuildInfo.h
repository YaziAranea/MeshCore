#pragma once

// UI and core versions are deliberately separate from the companion protocol.
// PlatformIO supplies the exact source identity; host tests/source ZIP builds
// without Git retain an explicit "unknown" rather than inventing a commit.
#ifndef SMARTUI_VERSION
#define SMARTUI_VERSION "0.09"
#endif
#ifndef SMARTUI_CORE_VERSION
#define SMARTUI_CORE_VERSION "1.17.1"
#endif
#ifndef SMARTUI_BUILD_SHA
#define SMARTUI_BUILD_SHA "unknown"
#endif
#ifndef SMARTUI_UPSTREAM_SHA
#define SMARTUI_UPSTREAM_SHA "a27e78e4"
#endif
