{/* Synthetic fixture: reproduces the DocTable layout of https://platform.kimi.ai/docs/pricing/chat.md with a few models. Prices are those the page listed on 2026-10-04. */}

# Model Inference Pricing Explanation

## Model Pricing

### K3 Series Models

<DocTable
  columns={[
{ title: "Model", width: "12%" },
{ title: "Unit", width: "10%" },
{ title: "Cache Write Price (TTL 5min)", width: "13%" },
{ title: "Cache Write Price (TTL 1h)", width: "13%" },
{ title: "Cached Input Price", width: "13%" },
{ title: "Input Price", width: "13%" },
{ title: "Output Price", width: "10%" },
{ title: "Context Window", width: "16%" },
]}
  rows={[
["kimi-k3", "1M tokens", <>{"$"}3.00</>, <>{"$"}6.00</>, <>{"$"}0.30</>, <>{"$"}3.00</>, <>{"$"}15.00</>, "1,048,576 tokens"],
]}
/>

### K2 Series Models

<DocTable
  columns={[
{ title: "Model", width: "24%" },
{ title: "Unit", width: "12%" },
{ title: "Input Price (Cache Hit)", width: "16%" },
{ title: "Input Price (Cache Miss)", width: "16%" },
{ title: "Output Price", width: "14%" },
{ title: "Context Window", width: "18%" },
]}
  rows={[
["kimi-k2.7-code", "1M tokens", <>{"$"}0.19</>, <>{"$"}0.95</>, <>{"$"}4.00</>, "262,144 tokens"],
["kimi-k2.6", "1M tokens", <>{"$"}0.16</>, <>{"$"}0.95</>, <>{"$"}4.00</>, "262,144 tokens"],
]}
/>
