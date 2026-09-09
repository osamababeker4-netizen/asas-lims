# ASAS LIMS 8.1.0

English UI covers static pages, dynamically rendered tables, status and priority labels, modal forms, messages, report previews, placeholders and import templates. Switching language preserves canonical option values and user-entered text. Uploaded documents remain in their original language.

The full-system Windows client uses Electron 44.3.0 with sandboxing, context isolation and no renderer Node integration. It loads the central web system and requires internet access. Windows distribution is portable and has no publisher code-signing certificate.

Android preview packages:
- `sa.asas.lims.portal.preview`: full central web system, file selection, location permission, print button and downloads.
- `sa.asas.lims.preview`: existing native field application updated to 8.1.0-preview, with its original local database and central sync architecture and corrected PDF sharing provider. A separate app ID protects the previously installed app. Its native screens retain the existing Arabic UI.

Both Android packages use development signing. They are separate preview installations, not in-place upgrades to an earlier production-signed app. No production signing key was available.

Validation: 9 existing server tests; browser checks for static and populated English pages, forms, report preview, enum value preservation, Arabic user text, language round-trip, desktop and mobile layout; Android Gradle builds. No production-account login or physical Android device validation was performed.
