#pragma once

// UI and core versions are deliberately separate from the companion protocol.
// PlatformIO supplies the exact source identity; host tests/source ZIP builds
// without Git retain an explicit "unknown" rather than inventing a commit.
#ifndef SMARTUI_VERSION
#define SMARTUI_VERSION "0.22"
#endif
#ifndef SMARTUI_CORE_VERSION
#define SMARTUI_CORE_VERSION "1.18.0"
#endif
#ifndef SMARTUI_BUILD_SHA
#define SMARTUI_BUILD_SHA "unknown"
#endif
#ifndef SMARTUI_UPSTREAM_SHA
#define SMARTUI_UPSTREAM_SHA "81dbae59"
#endif
