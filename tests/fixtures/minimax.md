{/* Synthetic fixture: reproduces the table layout of https://platform.minimax.io/docs/guides/pricing-paygo.md with a few models. Prices are those the page listed on 2026-10-07. */}

# Pay as You Go

## LLM

<Tabs>
  <Tab title="Standard">
    | Model | Input | Output | Prompt caching Read |
    | :- | :- | :- | :- |
    | **MiniMax-M3**<br />≤ 512k input tokens <span className="inline-flex">Permanent 50% off</span> | ~~\$0.60~~ \$0.30 / M tokens | ~~\$2.40~~ \$1.20 / M tokens | ~~\$0.12~~ \$0.06 / M tokens |
    | **MiniMax-M3**<br />> 512k input tokens\* <span className="inline-flex">Permanent 50% off</span> | ~~\$1.20~~ \$0.60 / M tokens | ~~\$4.80~~ \$2.40 / M tokens | ~~\$0.24~~ \$0.12 / M tokens |
  </Tab>

  <Tab title="Priority*">
    | Model | Input | Output | Prompt caching Read |
    | :- | :- | :- | :- |
    | **MiniMax-M3**<br />≤ 512k input tokens | ~~\$0.90~~ \$0.45 / M tokens | ~~\$3.60~~ \$1.80 / M tokens | ~~\$0.18~~ \$0.09 / M tokens |
  </Tab>
</Tabs>

| Model | Input | Output | Prompt caching Read | Prompt caching Write |
| :- | :- | :- | :- | :- |
| **MiniMax-M2.7** | \$0.3 / M tokens | \$1.2 / M tokens | \$0.06 / M tokens | \$0.375 / M tokens |
