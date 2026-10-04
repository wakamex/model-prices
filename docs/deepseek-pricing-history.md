# DeepSeek API pricing history, July to September 2026

DeepSeek's first-party API prices changed three times between July and September 2026, and models.dev recorded most of those changes late or not at all. This page records what DeepSeek charged in each period and the evidence behind each date, so the corrections and schedule in `data/` can be audited.

The short version: DeepSeek moved from flat pricing to peak and off-peak pricing at 16:00 UTC on August 16, 2026, charging twice the off-peak rate from 01:00 to 04:00 and 06:00 to 10:00 UTC. It cut the V4 Flash price when V4.1 Flash launched at 04:00 UTC on September 10. The weekday-only and Chinese public holiday exceptions to peak hours appeared on the pricing page later, without an announcement, and model-prices applies them from the start of peak pricing.

The evidence comes from DeepSeek's own changelog and news posts in English and Chinese, and from Internet Archive copies of its English and Chinese pricing pages, which bound when each change reached the page.

## Prices by period

Prices are USD per million tokens. From August 16 the listed rate is the off-peak rate, and the peak rate is twice it.

| Period (UTC) | V4 Flash input / cache hit / output | V4 Pro input / cache hit / output | Peak pricing |
|---|---|---|---|
| Until 2026-08-16 16:00 | $0.14 / $0.0028 / $0.28 | $0.435 / $0.003625 / $0.87 | None; one flat rate |
| 2026-08-16 16:00 to 2026-09-10 04:00 | $0.22 / $0.007 / $0.66 | $0.66 / $0.022 / $1.98 | 2x off-peak |
| From 2026-09-10 04:00 | $0.15 / $0.003 / $0.60 (V4.1 Flash, `deepseek-flash`) | $0.66 / $0.022 / $1.98 | 2x off-peak |

DeepSeek-V4-Flash-Vision-Exp launched on 2026-08-21 at V4 Flash prices. From 2026-09-10 the retired names `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are served by V4.1 Flash at its price.

## Peak-hour rule

The current rule, on the English pricing page: "Off-peak rates are half of the peak rates. Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday, excluding Chinese public holidays. All other hours are off-peak, including weekends and Chinese public holidays in full."

The Chinese page states the same rule in Beijing time: 9:00 to 12:00 and 14:00 to 18:00, Monday through Friday, excluding Chinese statutory holidays.

`model-prices check` compares both pages' wording with `schedules.toml` every day, so any change to the hours, the multiplier, or the exceptions fails the check.

## Announcements

- 2026-07-31, changelog: peak and off-peak pricing, off-peak at half the peak price, effective 2026-08-17 00:00 Beijing time, which is 2026-08-16 16:00 UTC. ([English](https://api-docs.deepseek.com/updates), [Chinese](https://api-docs.deepseek.com/zh-cn/updates))
- 2026-08-13, V4 Pro release note: repeats the same pricing change and effective time. ([English](https://api-docs.deepseek.com/news/news260813/), [Chinese](https://api-docs.deepseek.com/zh-cn/news/news260813))
- 2026-09-10, V4.1 Flash release note: lower V4.1 Flash prices from 04:00 UTC (12:00 Beijing time) on 2026-09-10, with peak pricing continuing. It also says V4 Pro requests would route to V4.1 Flash from 2026-09-14; a later changelog entry reversed that and kept V4 Pro at its existing billing. ([English](https://api-docs.deepseek.com/news/news260910/), [Chinese](https://api-docs.deepseek.com/zh-cn/news/news260910))

No changelog entry or release note in either language mentions weekends or holidays.

## Wording changes on the pricing pages

Each boundary is the last archived copy with the old wording and the first with the new.

| Change | Chinese page | English page |
|---|---|---|
| New prices and peak hours listed | [2026-08-16 16:13](https://web.archive.org/web/20260816161307/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) | [2026-08-16 17:14](https://web.archive.org/web/20260816171438/https://api-docs.deepseek.com/quick_start/pricing/) |
| Peak hours limited to Monday through Friday | between [2026-08-22 13:06](https://web.archive.org/web/20260822130627/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) and [2026-08-23 18:11](https://web.archive.org/web/20260823181111/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) | between [2026-08-22 14:16](https://web.archive.org/web/20260822141620/https://api-docs.deepseek.com/quick_start/pricing) and [2026-08-24 17:18](https://web.archive.org/web/20260824171826/https://api-docs.deepseek.com/quick_start/pricing/) |
| V4.1 Flash prices | [2026-09-10 08:40](https://web.archive.org/web/20260910084045/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) | [2026-09-15 14:22](https://web.archive.org/web/20260915142205/https://api-docs.deepseek.com/quick_start/pricing) (first archived copy after the change) |
| Chinese public holidays excluded | between [2026-09-17 23:31](https://web.archive.org/web/20260917233155/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) and [2026-09-19 10:10](https://web.archive.org/web/20260919101058/https://api-docs.deepseek.com/zh-cn/quick_start/pricing) | between [2026-09-17 05:14](https://web.archive.org/web/20260917051418/https://api-docs.deepseek.com/quick_start/pricing) and [2026-09-22 21:24](https://web.archive.org/web/20260922212416/https://api-docs.deepseek.com/quick_start/pricing) |

Because neither exception was announced, model-prices treats both as clarifications and applies the current rule from 2026-08-16 16:00 UTC. The only prices this affects are the peak hours of Saturday 2026-08-22, which are off-peak under the current rule; no Chinese public holiday fell between August 16 and September 17.

## Holidays

The holiday calendar in `schedules.toml` is the State Council's [2026 holiday schedule](https://www.gov.cn/zhengce/content/202511/content_7047090.htm), published 2025-11-04. It lists days off only. Weekend make-up workdays, such as 2026-09-20 and 2026-10-10, stay off-peak because DeepSeek's rule makes all weekends off-peak. The 2027 schedule is usually published in November and must be added before 2027.

## models.dev differences

- V4 Flash kept the flat $0.14 / $0.0028 / $0.28 until the V4.1 Flash update at 2026-09-10 16:10 UTC, twelve hours after the new prices took effect.
- V4 Pro still lists the flat $0.435 / $0.003625 / $0.87, while DeepSeek has charged $0.66 / $0.022 / $1.98 off-peak since 2026-08-16.
- models.dev records only off-peak rates; its DeepSeek files say so in a comment.

The corresponding entries in `corrections.toml` supply DeepSeek's rates for those periods, and `schedules.toml` supplies the peak multiplier.
