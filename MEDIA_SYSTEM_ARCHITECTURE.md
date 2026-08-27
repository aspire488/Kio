# Current media architecture — verified trace

`Telegram handle_message` calls `mini_kio.core.command_router.route`, which enters the pipeline classifier and resolves `MEDIA_PLAY` / `MEDIA_TRANSPORT` to `MediaManager`. `MediaManager` delegates YouTube work to `YouTubeProvider`: API and connector-scraped candidates are scored, a candidate URL is navigated, selected and loaded video IDs are compared, then extension player state and ad state are evaluated before a playing response.

The present hard failure was upstream of that media path: duplicate KIO runtime bootstrap created competing connector listeners and Telegram pollers. The named-mutex boundary now protects the entire runtime ownership domain rather than adding another media-local lock.

Known remaining design work after the connector is available: make structured recommendation intent the executor's canonical input, and make live player probes—not cached `MediaRegistry` state—the authority for state/control success messages.
