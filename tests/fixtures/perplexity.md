{/* Synthetic fixture: reproduces the price data embedded in https://docs.perplexity.ai/docs/getting-started/pricing.md with a few models. Prices are those the page listed on 2026-10-07. */}

# Pricing

export const PRICING = {
  "search": {
    "per1k": 5.00,
    "fastPer1k": 1.00
  },
  "sonar": {
    "models": [{
      "id": "sonar",
      "label": "Sonar",
      "input": 1,
      "output": 1,
      "request": {"low": 5, "medium": 8, "high": 12}
    }, {
      "id": "sonar-pro",
      "label": "Sonar Pro",
      "input": 3,
      "output": 15,
      "request": {"low": 6, "medium": 10, "high": 14}
    }]
  }
};
