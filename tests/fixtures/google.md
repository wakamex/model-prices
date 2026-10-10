<!-- Synthetic fixture: reproduces the table layout of https://ai.google.dev/gemini-api/docs/pricing.md.txt with a few models. Prices are those the page listed on 2026-09-30. -->

# Gemini Developer API pricing

## Gemini 3.8 Flash

*[`gemini-3.8-flash`](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)*

*`gemini-3.8-flash`*

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Free of charge | $0.75 through December 31, 2026. $1.50 starting January 1, 2027. |
| Output price (including thinking tokens) | Free of charge | $3.75 through December 31, 2026. $7.50 starting January 1, 2027. |
| Context caching price | Free of charge | $0.075 through December 31, 2026. $0.15 starting January 1, 2027. $0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026. $1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027. |
| Grounding with Google Search | Not available | 5,000 free search requests per month, then $14 per 1,000 requests. |

### Batch

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Not available | $0.375 through December 31, 2026. $0.75 starting January 1, 2027. |

## Gemini 3.8 Live, Gemini 3.8 Live Extended Thinking, and Gemini 3.1 Flash Live Preview

*[`gemini-3.8-live`](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live), [`gemini-3.8-live-extended-thinking`](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live-extended-thinking), and [`gemini-3.1-flash-live-preview`](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-live-preview)*

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Free of charge | $0.75 (text) $3.00 or $0.005/min (audio) $1.00 or $0.002/min (image/video) |
| Output price (including thinking tokens) | Free of charge | $4.50 (text) $12.00 or $0.018/min (audio) |

## Gemini Omni Flash Preview

*[`gemini-omni-flash-preview`](https://ai.google.dev/gemini-api/docs/models/gemini-omni-flash)*

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Not available | $1.50 (text / image / video / audio) |
| Output price (including thinking tokens) | Not available | $9.00 (text) $17.50 (video)^\*^ |

## Gemini 2.5 Pro

*[`gemini-2.5-pro`](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro)*

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Free of charge | $1.25, prompts \<= 200k tokens $2.50, prompts \> 200k tokens |
| Output price (including thinking tokens) | Free of charge | $10.00, prompts \<= 200k tokens $15.00, prompts \> 200k |
| Context caching price | Not available | $0.125, prompts \<= 200k tokens $0.25, prompts \> 200k $4.50 / 1,000,000 tokens per hour (storage price) |

## Gemini 2.5 Flash

*[`gemini-2.5-flash`](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)*

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Free of charge | $0.30 (text / image / video) $1.00 (audio) |
| Output price (including thinking tokens) | Free of charge | $2.50 |
| Context caching price | Not available | $0.03 (text / image / video) $0.1 (audio) $1.00 / 1,000,000 tokens per hour (storage price) |

## Gemini 3.8 Flash TTS

*[`gemini-3.8-flash-tts`](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts)*



Our 3.8 Flash Text-to-Speech audio model engineered for studio-grade voice fidelity, expressive acting, and long-form stability.

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Free of charge | $0.50 (text) through December 31, 2026. $1.00 (text) starting January 1, 2027. |
| Output price | Free of charge | $9.00 (audio) through December 31, 2026. $18.00 (audio) starting January 1, 2027. Equivalent to $0.00225 per 10s audio^\*^ through December 31, 2026. Equivalent to $0.0045 per 10s audio^\*^ starting January 1, 2027. |
| Used to improve our products | [Yes](https://ai.google.dev/gemini-api/terms) | [No](https://ai.google.dev/gemini-api/terms) |


## Gemini 3.1 Flash Image (Nano Banana 2) 🍌

*[`gemini-3.1-flash-image`](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image)*



Designed for speed and efficiency, the Gemini 3.1 Flash Image generation model is
effective for quick, interactive responses and high throughput.

### Standard

|   | Free Tier | Paid Tier, per 1M tokens in USD |
|---|---|---|
| Input price | Not available | $0.50 (text/image) |
| Output price | Not available | $3 (text and thinking) $60.00 (images) Equivalent to $0.045 per 0.5K image^\*^ $0.067 per 1K image^\*^, $0.101 per 2K image^\*^, and $0.151 per 4K image^\*^. |
| Grounding with Google Web and Image Search^\*\*^ | Not available^\*\*\*^ | 5,000 free search requests per month (shared across all Gemini 3 and newer models), then $14 per 1,000 requests for text and image-based grounding. |
| Used to improve our products | [Yes](https://ai.google.dev/gemini-api/terms) | [No](https://ai.google.dev/gemini-api/terms) |

