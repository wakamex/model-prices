<!-- Excerpt of https://ai.google.dev/gemini-api/docs/pricing.md.txt as served on 2026-11-04, keeping seven model sections whole. -->

# Gemini Developer API pricing

## Gemini 3.8 Flash  {% id="gemini-3.8-flash" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-3.8-flash`](/docs/models/gemini-3.8-flash)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-3.8-flash" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our most intelligent Flash model, engineered for long-horizon software
engineering, autonomous agents, and complex enterprise workflows.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.75 through December 31, 2026.   
  $1.50 starting January 1, 2027.

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $3.75 through December 31, 2026.   
  $7.50 starting January 1, 2027.

  ---

  * Context caching price
  * Free of charge
  * $0.075 through December 31, 2026.   
  $0.15 starting January 1, 2027.   
  $0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026.   
  $1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027.

  ---

  * Grounding with Google Search
  * Not available
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.375 through December 31, 2026.   
  $0.75 starting January 1, 2027.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.875 through December 31, 2026.   
  $3.75 starting January 1, 2027.

  ---

  * Context caching price
  * Not available
  * $0.0375 through December 31, 2026.   
  $0.075 starting January 1, 2027.   
  $0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026.   
  $1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.375 through December 31, 2026.   
  $0.75 starting January 1, 2027.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.875 through December 31, 2026.   
  $3.75 starting January 1, 2027.

  ---

  * Context caching price
  * Not available
  * $0.0375 through December 31, 2026.   
  $0.075 starting January 1, 2027.   
  $0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026.   
  $1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $1.35 through December 31, 2026.   
  $2.70 starting January 1, 2027.

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $6.75 through December 31, 2026.   
  $13.50 starting January 1, 2027.

  ---

  * Context caching price
  * Free of charge
  * $0.135 through December 31, 2026.   
  $0.27 starting January 1, 2027.   
  $0.50 / 1,000,000 tokens per hour (storage price) through December 31, 2026.   
  $1.00 / 1,000,000 tokens per hour (storage price) starting January 1, 2027.

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Contributor" %}
  {% callout type="note" %}
  The Gemini API Contributor Tier is offered as a private preview on an
      invite-only basis. Speed and reliability are equivalent to
      [Standard Tier inference](/docs/optimization). Eligible users will be invited by
      email and see a callout in AI Studio.

  {% /callout %}

  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD{% sup %}*{% /sup %}

  ---

  * Input price
  * Free of charge
  * $0.375

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $1.875

  ---

  * Context caching price
  * Free of charge
  * $0.0375   
  $0.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [Yes](/docs/logs-policy#contributor-tier)
  {% /table %}

  {% sup %}*{% /sup %} Discounts and model availability are subject to change.
    

  {% /tab %}

{% /tabs %}

## Gemini Omni Flash  {% id="gemini-omni-1.1-flash" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-omni-1.1-flash`](/docs/models/gemini-omni-flash)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-omni-1.1-flash" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our next-generation video generation and editing model, now generally available
to developers on the paid tier of the Gemini API.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $1.50 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $9.00 (text)    
  $17.50 (video){% sup %}*{% /sup %}

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}

{% sup %}*{% /sup %} Billing is based on total output token consumption,
calculated at a rate of 5,792 tokens per second of 720p video. Under Standard
pricing, this equates to an effective price of approximately $0.10 per second.

## Gemini 3.8 Live, Gemini 3.8 Live Extended Thinking, and Gemini 3.1 Flash Live Preview  {% id="gemini-3.8-live" %}

{% two-column-layout %}
  

  {% left-column class="center-vertically" %}
  *[`gemini-3.8-live`](/docs/models/gemini-3.8-live),
    [`gemini-3.8-live-extended-thinking`](/docs/models/gemini-3.8-live-extended-thinking),
    [`gemini-3.1-flash-live-preview`](/docs/models/gemini-3.1-flash-live-preview)*

  {% /left-column %}

  

  {% right-column class="center-vertically right-align" %}
   {% button href="https://aistudio.google.com/live?model=gemini-3.8-live" variant="ais" %} Try it in Google AI Studio {% /button %}

  {% /right-column %}

  

{% /two-column-layout %}

{% hr /%}

Our low-latency, audio-to-audio models optimized for real-time dialogue with
acoustic nuance detection, numeric precision, and multimodal awareness.

{% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.75 (text)    
    $3.00 or $0.005/min (audio)    
    $1.00 or $0.002/min (image/video)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $4.50 (text)    
    $12.00 or $0.018/min (audio)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Supported
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
    then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
{% /table %}

{% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
more queries to Google Search. You will be charged for each individual search
query performed.

## Gemini 3.1 Flash Image (Nano Banana 2) 🍌  {% id="gemini-3.1-flash-image" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-3.1-flash-image`](/docs/models/gemini-3.1-flash-image)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-image" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Designed for speed and efficiency, the Gemini 3.1 Flash Image generation model
is effective for quick, interactive responses and high throughput.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.50 (text/image)

  ---

  * Output price
  * Not available
  * $3 (text and thinking)    
  $60.00 (images)    
  Equivalent to $0.045 per 0.5K image{% sup /%}    
  $0.067 per 1K image{% sup /%},    
  $0.101 per 2K image{% sup /%},    
  and $0.151 per 4K image{% sup /%}.

  ---

  * Grounding with Google Web and Image Search{% sup %}**{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests for text and image-based grounding (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}

{% sup %}*{% /sup %} Image output is priced at $60 per 1,000,000 tokens. Output
images at 0.5K (512px) consume 747 tokens and are equivalent to $0.045 per
image. Output images at 1K (1024x1024px) consume 1120 tokens and are equivalent
to $0.067 per image. Output images at 2K (2048x2048px) consume 1680 tokens and
are equivalent to $0.101 per image. Output images at 4K (4096x4096px) consume
2520 tokens and are equivalent to $0.151 per image.

## Gemini 3.8 Flash TTS  {% id="gemini-3.8-flash-tts" %}

{% two-column-layout %}
  {% left-column %}
  *[`gemini-3.8-flash-tts`](/docs/models/gemini-3.8-flash-tts)*

  {% /left-column %}

  {% right-column %}
  {% button class="right-align" href="https://aistudio.google.com/prompts/new_chat?model=gemini-3.8-flash-tts" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our 3.8 Flash Text-to-Speech audio model engineered for studio-grade voice fidelity, expressive acting, and long-form stability.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.50 (text) through December 31, 2026.   
  $1.00 (text) starting January 1, 2027.

  ---

  * Output price
  * Free of charge
  * $9.00 (audio) through December 31, 2026.   
  $18.00 (audio) starting January 1, 2027.   
  Equivalent to $0.00225 per 10s audio{% sup /%} through December 31, 2026.   
  Equivalent to $0.0045 per 10s audio{% sup /%} starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.25 (text) through December 31, 2026.   
  $0.50 (text) starting January 1, 2027.

  ---

  * Output price
  * Not available
  * $4.50 (audio) through December 31, 2026.   
  $9.00 (audio) starting January 1, 2027.   
  Equivalent to $0.001125 per 10s audio{% sup /%} through December 31, 2026.   
  Equivalent to $0.00225 per 10s audio{% sup /%} starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.25 (text) through December 31, 2026.   
  $0.50 (text) starting January 1, 2027.

  ---

  * Output price
  * Not available
  * $4.50 (audio) through December 31, 2026.   
  $9.00 (audio) starting January 1, 2027.   
  Equivalent to $0.001125 per 10s audio{% sup /%} through December 31, 2026.   
  Equivalent to $0.00225 per 10s audio{% sup /%} starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.90 (text) through December 31, 2026.   
  $1.80 (text) starting January 1, 2027.

  ---

  * Output price
  * Free of charge
  * $16.20 (audio) through December 31, 2026.   
  $32.40 (audio) starting January 1, 2027.   
  Equivalent to $0.00405 per 10s audio{% sup /%} through December 31, 2026.   
  Equivalent to $0.0081 per 10s audio{% sup /%} starting January 1, 2027.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}

{% sup %}*{% /sup %} Audio tokens correspond to 25 tokens per second of audio.

## Gemini 2.5 Pro  {% id="gemini-2.5-pro" %}

*[`gemini-2.5-pro`](/docs/models/gemini-2.5-pro)*

{% hr /%}

{% callout type="caution" %}
  Gemini 2.5 Pro (`gemini-2.5-pro`) is
  [deprecated](/docs/deprecations#gemini-2.5-pro-models) and is no longer
  available to select in Google AI Studio. Effective December 1, 2026, all API
  requests to `gemini-2.5-pro` will automatically route to
  [Gemini 3.8 Flash (`gemini-3.8-flash`)](/docs/models/gemini-3.8-flash) and be
  billed at [Gemini 3.8 Flash rates](/docs/pricing#gemini-3.8-flash).

{% /callout %}

A Pro model which excels at coding and complex reasoning tasks.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $1.25, prompts <= 200k tokens    
  $2.50, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $10.00, prompts <= 200k tokens    
  $15.00, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.125, prompts <= 200k tokens    
  $0.25, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free), then $35 / 1,000 grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * 10,000 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.625, prompts <= 200k tokens    
  $1.25, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $5.00, prompts <= 200k tokens    
  $7.50, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.125, prompts <= 200k tokens    
  $0.25, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free), then $35 / 1,000 grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.625, prompts <= 200k tokens    
  $1.25, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $5.00, prompts <= 200k tokens    
  $7.50, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.125, prompts <= 200k tokens    
  $0.25, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free), then $35 / 1,000 grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $2.25, prompts <= 200k tokens    
  $4.50, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $18.00, prompts <= 200k tokens    
  $27.00, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.225, prompts <= 200k tokens    
  $0.45, prompts > 200k    
  $8.10 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free), then $35 / 1,000 grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * 10,000 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}

## Gemini 2.5 Flash  {% id="gemini-2.5-flash" %}

*[`gemini-2.5-flash`](/docs/models/gemini-2.5-flash)*

{% hr /%}

{% callout type="caution" %}
  Gemini 2.5 Flash (`gemini-2.5-flash`) is
  [deprecated](/docs/deprecations#gemini-2.5-flash-models) and is no longer
  available to select in Google AI Studio. Effective December 1, 2026, all API
  requests to `gemini-2.5-flash` will automatically route to
  [Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`)](/docs/models/gemini-3.5-flash-lite)
  and be billed at
  [Gemini 3.5 Flash-Lite rates](/docs/pricing#gemini-3.5-flash-lite).

{% /callout %}

Our first hybrid reasoning model which supports a 1M token context window and
has thinking budgets.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.30 (text / image / video)    
  $1.00 (audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $2.50

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Free of charge, up to 500 RPD (limit shared with Flash-Lite RPD)
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * 500 RPD
  * 1,500 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.15 (text / image / video)    
  $0.50 (audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.15 (text / image / video)    
  $0.50 (audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.54 (text / image / video)    
  $1.80 (audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $4.50

  ---

  * Context caching price
  * Not available
  * $0.054 (text / image / video)    
  $0.18 (audio)    
  $1.80 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Free of charge, up to 500 RPD (limit shared with Flash-Lite RPD)
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * 500 RPD
  * 1,500 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}
