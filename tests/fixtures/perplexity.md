{/* Synthetic fixture: reproduces two tabs of https://docs.perplexity.ai/docs/agent-api/models.md, with prices it listed on 2026-10-19. */}

# Agent API Models

<Tabs>
  <Tab title="Anthropic">
    <Card title="Anthropic">
      Claude Opus (highest reasoning), Sonnet (balanced), and Haiku (fastest, cheapest).
    </Card>

    | Model | Input (\$/1M) | Output (\$/1M) | Cache read (\$/1M) | Service tiers | Docs |
    | - | - | - | - | - | - |
    | `anthropic/claude-fable-5` | 10.00 | 50.00 | 1.00 | — | [Claude Fable 5](https://platform.claude.com/docs/en/about-claude/models/introducing-claude-fable-5-and-claude-mythos-5) |
    | `anthropic/claude-opus-5-5` | 4.00 | 20.00 | 0.20 | — | [Claude Opus 5.5](https://platform.claude.com/docs/en/about-claude/models/overview) |
    | `anthropic/claude-opus-5` | 5.00 | 25.00 | 0.50 | — | [Claude Opus 5](https://platform.claude.com/docs/en/about-claude/models/overview) |
    | `anthropic/claude-sonnet-5-5` | 2.00 | 10.00 | 0.10 | — | [Claude Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5) |
    | `anthropic/claude-sonnet-5` | 2.00 | 10.00 | 0.20 | — | [Claude Sonnet 5](https://platform.claude.com/docs/en/about-claude/models/whats-new-sonnet-5) |
    | `anthropic/claude-haiku-5-5` | 0.10 (≤100k)<br />0.50 (>100k) | 0.50 (≤100k)<br />2.50 (>100k) | 0.01 (≤100k)<br />0.05 (>100k) | — | [Claude Haiku 5.5](https://platform.claude.com/docs/en/about-claude/models/overview) |

    <Warning>
      Requests that use an `anthropic/*` model must include `max_output_tokens`. If omitted, the API returns HTTP 400 with `validation failed: max_output_tokens is required when using Anthropic models`. `max_output_tokens` is a shared Agent API parameter, but this required condition applies only to Anthropic models.
    </Warning>
  </Tab>

  <Tab title="Perplexity">
    <Card title="Perplexity">
      Perplexity's grounded search model.
    </Card>

    | Model | Input (\$/1M) | Output (\$/1M) | Cache read (\$/1M) | Service tiers | Docs |
    | - | - | - | - | - | - |
    | `perplexity/sonar` | 0.25 | 2.50 | 0.0625 | — | — |
  </Tab>
</Tabs>
