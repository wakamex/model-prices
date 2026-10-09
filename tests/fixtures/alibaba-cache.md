<!-- Synthetic fixture: reproduces the structure of https://www.alibabacloud.com/help/en/model-studio/context-cache.md, with model lists and billing rules it gave on 2026-10-09. -->
# Context Cache

## Explicit cache <span id="825f201c5fy6o" />

### Supported models <span id="29f4500309mmr" />

<Tabs>
  <Tab title="Singapore">
    > The following models are available in the International deployment scope.

    - Qwen Max: qwen3.8-max, qwen3.7-max
    - Qwen Plus: qwen3.5-plus-2026-04-20, qwen3.7-plus-2026-05-26
  </Tab>
  <Tab title="China (Beijing)">
    - Qwen Plus: qwen3-coder-unlisted
  </Tab>
</Tabs>

### Billing <span id="904e3da8aatwp" />

- <strong>Cache creation</strong>: Content used to create a new cache is billed at 125% of the standard input token price.
- <strong>Cache hit</strong>: Billed at 10% of the standard input token price.
- <strong>Exception</strong>: The explicit cache hit price for qwen3.8-max is not 10% of the standard input token price.

## Implicit cache <span id="2317ea09cfxok" />

### Supported models <span id="3a87ca9564291" />

<Tabs>
  <Tab title="Singapore">
    - Qwen Max: qwen3.8-max, qwen3.7-max, qwen3-max-preview
    - Qwen Plus: qwen3.7-plus-2026-05-26
  </Tab>
</Tabs>

### Billing <span id="7768a4362ailr" />

- For models other than qwen3.8-max: The unit price of `cached_token` is <strong>20%</strong> of the `input_token` unit price.
