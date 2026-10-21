# OSVED — Telegram emoji library

Default style: **balanced**. Keep headings readable, use contextual icons sparingly, and never alter the article's factual text. Custom emoji are presentation only.

## Registered sticker-set short names
- https://t.me/addemoji/tgiosicons
- https://t.me/addemoji/wbwrr_emoji
- https://t.me/addemoji/CheekspinkShoutoEmoji
- https://t.me/addemoji/picardiemoj
- https://t.me/addemoji/Ordinary_Human
- https://t.me/addemoji/Fric_TheFrog
- https://t.me/addemoji/Animalspart2ShoutoEmoji
- https://t.me/addemoji/PetsMemesEmoji
- https://t.me/addemoji/berserkemojixoley
- https://t.me/addemoji/AdaptivePixelEmoji
- https://t.me/addemoji/RestrictedEmoji
- https://t.me/addemoji/FlameEmoji
- https://t.me/addemoji/cyberslav_by_TgEmodziBot
- https://t.me/addemoji/adaptiveqp_by_emsetbot
- https://t.me/addemoji/soyacorp_emojipack

These links are candidates, not proof that each sticker or its ID is accessible. Additional sets can be registered freely. Never infer custom_emoji_id from a public sticker-set short name.

## Configuring real custom emoji
Use the Telegram Bot API `getStickerSet` with a short name above, examine sticker records and select verified `custom_emoji_id` values. Ensure the bot can send them in the target chat. Do not commit bot tokens, credentials, or personal sessions.

On deployment, add `/opt/osved/app/config/emoji_ids.json` with role-to-ID mapping, e.g. `{"news": "REPLACE_WITH_VERIFIED_NUMERIC_ID"}`. Numeric verified IDs only. Missing/invalid mappings use standard Unicode icons automatically. The deployed compose config folder is read-only inside the container, so edit the host copy.

Supported roles: `news`, `source`, `security`, `ai`, `development`, `business`.

An emoji cannot by itself validate a source. Telegram HTML supports `<tg-emoji emoji-id="…">fallback</tg-emoji>`; if permissions are insufficient, use Unicode fallback rather than guessing an ID.
