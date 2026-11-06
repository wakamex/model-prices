<!-- Copy of https://docs.modelstudio.console.alibabacloud.com/en/model-studio/token-plan-personal-overview.md as served on 2026-11-06. -->
> ## Documentation Index
> Fetch the complete documentation index at: https://docs.modelstudio.console.alibabacloud.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Overview

> Token Plan Personal Edition is an AI large model subscription service for individual developers. It uses Credits as a unified billing unit and supports text models, multimodal models, and Harness tools. It is compatible with mainstream AI coding and agent tools.

<meta property="og:title" content="Overview" />

<Note>
  Token Plan Personal Edition is currently available only in the <strong>Singapore</strong> region.
</Note>

## Key features <span id="tpp01-h-features" />

- <strong>Unified Credits billing</strong>: Use Credits to pay for different models and Harness tools under a single billing unit.
- <strong>Multimodal model support</strong>: Covers text generation, reasoning, visual understanding, image generation, speech synthesis, real-time voice conversation, speech recognition, video generation, and more.
- <strong>Harness tool integration</strong>: Supports web search, text-to-image search, image-to-image search, web scraping, and code interpreter.
- <strong>Usage packs</strong>: When the plan's monthly quota is insufficient, purchase usage packs to add Credits (20,000 Credits per pack, up to 5 packs at a time).
- <strong>Compatible with multiple tools</strong>: Works with mainstream AI coding and agent tools such as Claude Code, Cursor, Qwen Code, Qoder and OpenClaw.

## Plans and pricing <span id="tpp01-h-pricing" />

<table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "14%" }} /><col style={{ width: "24%" }} /><col style={{ width: "24%" }} /><col style={{ width: "19%" }} /><col style={{ width: "19%" }} /></colgroup><thead><tr><th style={{ verticalAlign: "top" }} /><th style={{ verticalAlign: "top" }}><p><strong>Lite plan</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Essential plan</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Standard plan</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Pro plan</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p><strong>Pricing</strong></p></td><td style={{ verticalAlign: "top" }}><p style={{ lineHeight: "1.8" }}><strong>\$6/month</strong><br /><span style={{ display: "block", marginTop: "6px" }}><a href="#tpp01-h-new-user-promo" style={{ color: "var(--color-primary, #5266ff)", textDecoration: "underline" }}>Limited-time new-user price</a> <strong>\$3/month</strong></span></p></td><td style={{ verticalAlign: "top" }}><p style={{ lineHeight: "1.8" }}><strong>\$10/month</strong><br /><span style={{ display: "block", marginTop: "6px" }}><a href="#tpp01-h-new-user-promo" style={{ color: "var(--color-primary, #5266ff)", textDecoration: "underline" }}>Limited-time new-user price</a> <strong>\$5/month</strong></span></p></td><td style={{ verticalAlign: "top" }}><p><strong>\$18/month</strong></p></td><td style={{ verticalAlign: "top" }}><p><strong>\$68/month</strong></p></td></tr><tr><td style={{ verticalAlign: "top" }}><p><strong>Monthly quota</strong></p></td><td style={{ verticalAlign: "top" }}><p>11,500 Credits</p></td><td style={{ verticalAlign: "top" }}><p>25,500 Credits</p></td><td style={{ verticalAlign: "top" }}><p>45,000 Credits</p></td><td style={{ verticalAlign: "top" }}><p>180,000 Credits</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p><strong>Concurrent Agents</strong></p></td><td style={{ verticalAlign: "top" }}><p>1-2</p></td><td style={{ verticalAlign: "top" }}><p>2-3</p></td><td style={{ verticalAlign: "top" }}><p>3-4</p></td><td style={{ verticalAlign: "top" }}><p>6-8</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p><strong>Benefits</strong></p></td><td style={{ verticalAlign: "top" }}><p>Multimodal models</p> <p>Harness tools</p> <p>Mainstream tools</p></td><td style={{ verticalAlign: "top" }}><p>All Lite benefits</p></td><td style={{ verticalAlign: "top" }}><p>All Lite benefits</p> <p>Harness benefits</p></td><td style={{ verticalAlign: "top" }}><p>All Standard benefits</p> <p>Higher concurrency</p> <p>Harness benefits</p></td></tr></tbody></table>

<span id="tpp01-h-new-user-promo" />

<Note>
  The limited-time new-user price is available until 23:59:59 on November 30, 2026 (UTC+8) and is limited to accounts that have never purchased a Token Plan Personal Edition subscription.
</Note>

- <strong>Monthly quota</strong>: The quota is calculated per subscription month. When the plan quota is used up and no usage bundle Credits are available, the service is paused until the next subscription month.
- <strong>Extra Bundle</strong>: Priced at \$15/bundle/month, with 20,000 Credits per bundle. Requires an active subscription before purchase, hold up to 5 at the same time; after the plan's monthly quota is used up, usage bundle Credits are deducted automatically.

After the monthly quota is used up, you can purchase an Extra Bundle for additional Credits, or wait for the quota to reset at the start of the next subscription month. Unused quota within a subscription month does not carry over to the next cycle.

## Credits billing mechanism <span id="tpp01-h-credits" />

<Note>
  Multimodal models such as video generation consume significantly more Credits per call than text conversations. Pay attention to the following two points:

  - <strong>High consumption per call</strong>: Credits for video generation increase with the duration and resolution, which may quickly use up a large part of your quota. For your first attempts, use a shorter duration and a lower resolution, check the actual consumption per call on the subscription page usage details in the console, and then decide on further usage.
  - <strong>Batch settlement for asynchronous tasks</strong>: Credits for asynchronous tasks such as video generation are settled after the task completes, rather than deducted at submission. If you submit multiple asynchronous tasks within a short period, the Credits settled together after all the tasks complete may cause you to reach the quota limit quickly.
</Note>

### Billing description <span id="tpp01-h-credits-desc" />

The Credits consumed per request are dynamically determined by model type, token usage, thinking mode, and tool calls. Refer to the [subscription page](https://modelstudio.console.alibabacloud.com/ap-southeast-1/subscription/token-plan/personal) usage details in the console for actual consumption.

### Deduction order <span id="tpp01-h-deduction" />

1. Credits consumed by each call are deducted from the plan quota of the current subscription month first.
2. After the plan's monthly quota is used up, usage bundle Credits are automatically deducted. When usage bundle Credits are also used up or not held, the service is paused. You can upgrade to a higher-tier plan, or wait for the quota to reset at the start of the next subscription month.

### Quota reset <span id="tpp01-h-quota-reset" />

The quota resets automatically per subscription month: at the start of each subscription month, the plan quota is restored to the full monthly quota of the corresponding tier. When the weekly quota was removed on September 22, 2026, the remaining quota of existing subscriptions was reset once to the full monthly quota of their plan tier on that day, with subscription periods and expiration dates unchanged.

## Supported models <span id="tpp01-h-models" />

<Tip>
  - <strong>Limited-time night discount (60% off)</strong>: Invocations between 22:00 and 08:00 (UTC+8) enjoy 60% off Credits consumption for qwen3.8-max and qwen3.8-flash.
  - <strong>Limited-time night discount (50% off)</strong>: Invocations between 22:00 and 08:00 (UTC+8) enjoy 50% off Credits consumption for deepseek-v4-pro-0813, deepseek-v4-flash-0731, deepseek-v4.1-flash, and deepseek-v4.1-flash-1017.
  - <strong>qwen3.8-max-preview retired</strong>: The original model ID still works, and requests are automatically routed to qwen3.8-max, with Credits consumption and usage statistics calculated at the qwen3.8-max rate. Update the model ID in your configuration to qwen3.8-max.

  Alibaba Cloud Model Studio reserves the right to modify or adjust promotions based on operational needs, including but not limited to promotion details and validity periods. Please refer to the latest page content or Alibaba Cloud notifications.
</Tip>

<Tabs>
  <Tab title="Qwen">
    <table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "35%" }} /><col style={{ width: "65%" }} /></colgroup><thead style={{ verticalAlign: "top" }}><tr><th style={{ verticalAlign: "top" }}><p><strong>Model ID</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>auto</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p><p>An intelligent model provided by the platform that automatically matches an underlying model for each request, balancing quality and cost.</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen3.8-max</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen3.8-flash</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen3.7-max</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen3.7-plus</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen3.6-flash</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen-image-3.0-pro</p></td><td style={{ verticalAlign: "top" }}><p>Image generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen-audio-3.0-tts-plus</p></td><td style={{ verticalAlign: "top" }}><p>Speech synthesis</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen-audio-3.0-realtime-plus</p></td><td style={{ verticalAlign: "top" }}><p>Real-time voice conversation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>qwen-audio-3.0-asr-flash</p></td><td style={{ verticalAlign: "top" }}><p>Speech recognition</p></td></tr></tbody></table>
  </Tab>

  <Tab title="Wanx">
    <table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "35%" }} /><col style={{ width: "65%" }} /></colgroup><thead style={{ verticalAlign: "top" }}><tr><th style={{ verticalAlign: "top" }}><p><strong>Model ID</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>wan2.7-image</p></td><td style={{ verticalAlign: "top" }}><p>Image generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>wan2.7-image-pro</p></td><td style={{ verticalAlign: "top" }}><p>Image generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>wan3.0-video</p></td><td style={{ verticalAlign: "top" }}><p>Video generation</p></td></tr></tbody></table>
  </Tab>

  <Tab title="DeepSeek">
    <table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "35%" }} /><col style={{ width: "65%" }} /></colgroup><thead style={{ verticalAlign: "top" }}><tr><th style={{ verticalAlign: "top" }}><p><strong>Model ID</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>deepseek-v4.1-flash</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>deepseek-v4.1-flash-1017</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, visual understanding, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>deepseek-v4-pro</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>deepseek-v4-pro-0813</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>deepseek-v4-flash-0731</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr></tbody></table>
  </Tab>

  <Tab title="Zhipu AI">
    <table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "35%" }} /><col style={{ width: "65%" }} /></colgroup><thead style={{ verticalAlign: "top" }}><tr><th style={{ verticalAlign: "top" }}><p><strong>Model ID</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>glm-5.3</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>glm-5.2</p></td><td style={{ verticalAlign: "top" }}><p>Reasoning, text generation</p></td></tr></tbody></table>
  </Tab>

  <Tab title="HappyHorse">
    <table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "35%" }} /><col style={{ width: "65%" }} /></colgroup><thead style={{ verticalAlign: "top" }}><tr><th style={{ verticalAlign: "top" }}><p><strong>Model ID</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>happyhorse-1.1-i2v</p></td><td style={{ verticalAlign: "top" }}><p>Video generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>happyhorse-1.1-t2v</p></td><td style={{ verticalAlign: "top" }}><p>Video generation</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>happyhorse-1.1-r2v</p></td><td style={{ verticalAlign: "top" }}><p>Video generation</p></td></tr></tbody></table>
  </Tab>
</Tabs>

## Supported Harness tools <span id="tpp01-h-harness" />

<table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "40%" }} /><col style={{ width: "60%" }} /></colgroup><thead><tr><th style={{ verticalAlign: "top" }}><p><strong>Capability</strong></p></th><th style={{ verticalAlign: "top" }}><p><strong>Tool name</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>Web search</p></td><td style={{ verticalAlign: "top" }}><p>web\_search</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Text-to-image search</p></td><td style={{ verticalAlign: "top" }}><p>web\_search\_image</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Image-to-image search</p></td><td style={{ verticalAlign: "top" }}><p>image\_search</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Web scraping</p></td><td style={{ verticalAlign: "top" }}><p>web\_extractor</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Code interpreter</p></td><td style={{ verticalAlign: "top" }}><p>code\_interpreter</p></td></tr></tbody></table>

## Subscription management <span id="tpp01-h-sub-mgmt" />

### Upgrade <span id="tpp01-h-upgrade" />

You can upgrade from a lower-tier plan to a higher-tier plan. Upgrades do not reset the current subscription cycle: you pay the prorated price difference for the remaining days of the current cycle, the current cycle only receives additional Credits prorated based on the quota difference, and the new tier's monthly quota applies from the next subscription month.

The Credits granted upon upgrade are not the full monthly quota of the new plan tier. Instead, they are prorated based on the price difference you actually paid and the number of days remaining in your current billing cycle:

```plaintext
Upgrade price difference = (New plan price − Old plan price) × Remaining days / 30
(Less than one day counts as one day)

Additional quota for the current cycle = Remaining days / 30 × (Monthly quota after upgrade − Monthly quota before upgrade)
(Less than one day counts as one day; the result is rounded up)
```

The actual upgrade fee is subject to the price breakdown shown on the payment page.

For example, if you subscribe to the Lite plan (\$6/month, 11,500 Credits monthly quota) on September 2 and upgrade to the Essential plan (\$10/month, 25,500 Credits monthly quota) on September 12 with 20 days remaining in the current cycle: the price difference is (10 − 6) × 20 / 30 ≈ 2.67 USD, and the additional quota for the current cycle is 20 / 30 × (25,500 − 11,500) ≈ 9,334 Credits (rounded up).

### Renewal <span id="tpp01-h-renew" />

You can switch to a different renewal duration and renew for multiple cycles at once.

- <strong>Manual renewal</strong>: You can choose a different renewal duration and renew for multiple cycles.
- <strong>Auto-renewal</strong>: When enabled, the system automatically deducts fees and renews before expiration.

Renewal only extends the subscription validity period and does not add quota to the current billing cycle.

### Other <span id="tpp01-h-notice" />

- The Personal Edition does not currently support unsubscription.
- If your subscription expires, your API Key becomes unavailable; after you repurchase, the original API Key becomes usable again and no reconfiguration is required in your tools.

## Important information before subscribing <span id="tpp01-h-pre-notice" />

1. <strong>Usage scope</strong>: This plan is intended for interactive use only within coding tools and agent tools such as Claude Code, Cursor, Qwen Code, Qoder and OpenClaw. It must not be used for automation scripts, custom application backends, or any non-interactive batch call scenarios. Models are accessed through the tools' extension mechanisms (Skill, Slash Command, or Agent); calls initiated interactively within a tool are considered normal use. Using the plan API Key for calls outside the allowed scope will be considered a violation or abuse, and may result in subscription suspension or API Key banning.
2. <strong>Region and data transfer</strong>: For Token Plan, the only available region is Singapore and the only available deployment mode is Global, which means the model inference will be performed globally. The prompts and model outputs will involve cross-border data transfer, and you are responsible for ensuring that your use of the Token Plan complies with applicable laws and regulations.
3. <strong>Account usage policy</strong>: The plan is for the exclusive use of the subscriber and sharing is prohibited. Account sharing may result in restricted subscription benefits.
4. <strong>Purchase limit</strong>: Each verified identity is limited to one subscription per edition, and can hold the Personal Edition and Team Edition at the same time.
5. <strong>Device usage</strong>: You can configure the same API Key on multiple devices you own (such as your home and office computers), but the Personal Edition is for your exclusive use. Sharing the API Key with others may be considered a violation and result in suspension.
6. <strong>RAM user identity verification</strong>: RAM users do not need to complete identity verification separately. As long as the Alibaba Cloud account has completed identity verification and has assigned the RAM user a seat and API call permission, the RAM user can use Token Plan normally.
