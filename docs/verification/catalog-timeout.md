# Startup with a populated App Engine — 1.2.2

A normal first installation on an Apple Silicon Mac reused a running App Engine
with 45 apps. Its `/api/apps` response took 1.23 seconds, exceeding the launcher's
0.6-second identity-probe timeout. The signed app copied into Applications but
could not discover or install the game. No existing engine was stopped.

The coordinator now permits 10 seconds for app enumeration, writable-root lookup,
and catalog refresh. Engine identity probes retain the short timeout. Origin,
redirect, URL validation, file preservation, and phone security rules are unchanged.

Three real-HTTP regressions inject a 1.1-second delay in those endpoints. Each
failed before the change and passed afterwards. Focused launcher, bundle, and
phone-entrypoint checks: 60 passed, plus 15 subtests. Independent review found no
blocking issues.

The extracted universal 1.2.2 app passed strict deep signature verification and
both architecture qualification workflows using isolated homes and ports. The
arm64 workflow exercised paired-phone gameplay; x86_64 exercised local gameplay
and the separate host window. Both exercised install, relaunch and engine restart.
The offline build audited 25 Mach-O deployment targets. All payload hashes match.

On the actual Mac, the corrected app then installed into `~/Applications`, added
the game to the existing engine, and opened the setup screen in Chrome with
“Phone hosting ready.” This is a real current-macOS launch, not a macOS 12.6 or
physical iPhone qualification. Fonts, colors, gameplay and game assets are unchanged.
