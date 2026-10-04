{/* Synthetic fixture: reproduces the MDX table layout of https://www.alibabacloud.com/help/en/model-studio/model-pricing.md with a few models. Prices are those the page listed on 2026-10-04. */}

# Model inference pricing

## Text generation - Qwen <span id="t1" />

### Qwen-Plus <span id="t2" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead>
        <tr>
          <th rowSpan={2}><strong>Model ID</strong></th>
          <th rowSpan={2}><strong>Deployment scope</strong></th>
          <th rowSpan={2}><strong>Input tokens per request</strong></th>
          <th rowSpan={2}><strong>Input price (per 1 million tokens)</strong></th>
          <th colSpan={2}><strong>Output price (per 1 million tokens)</strong></th>
          <th rowSpan={2}><strong>Free quota</strong></th>
        </tr>
        <tr>
          <th>Non-Thinking mode</th>
          <th>Thinking mode (chain of thought + answer)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td rowSpan={2}>qwen3.7-plus
          > Currently equivalent to qwen3.7-plus-2026-05-26</td>
          <td rowSpan={2}>International</td>
          <td>0\<Token≤256K</td>
          <td>List price \$0.4 (Limited-time 20% off)</td>
          <td>List price \$1.6 (Limited-time 20% off)</td>
          <td>List price \$1.6 (Limited-time 20% off)</td>
          <td rowSpan={2}>1 million tokens</td>
        </tr>
        <tr>
          <td>256K\<Token≤1M</td>
          <td>List price \$1.2 (Limited-time 20% off)</td>
          <td>List price \$4.8 (Limited-time 20% off)</td>
          <td>List price \$4.8 (Limited-time 20% off)</td>
        </tr>
      </tbody>
    </table>
  </Tab>
  <Tab title="China (Beijing)">
    <table>
      <thead>
        <tr>
          <th><strong>Model ID</strong></th>
          <th><strong>Input price (per 1 million tokens)</strong></th>
          <th><strong>Output price (per 1 million tokens)</strong></th>
        </tr>
      </thead>
      <tbody>
        <tr><td>qwen3.7-plus</td><td>\$0.115</td><td>\$0.459</td></tr>
      </tbody>
    </table>
  </Tab>
</Tabs>

### Qwen-Turbo <span id="t3" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead>
        <tr>
          <th rowSpan={2}><strong>Model ID</strong></th>
          <th rowSpan={2}><strong>Deployment scope</strong></th>
          <th rowSpan={2}><strong>Input price (per 1 million tokens)</strong></th>
          <th colSpan={2}><strong>Output price (per 1 million tokens)</strong></th>
        </tr>
        <tr>
          <th>Non-Thinking mode</th>
          <th>Thinking mode (chain of thought + answer)</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>qwen-turbo</td><td>International</td><td>\$0.05</td><td>\$0.2</td><td>\$0.5</td></tr>
      </tbody>
    </table>
  </Tab>
</Tabs>

### Qwen-Omni <span id="t4" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead>
        <tr>
          <th rowSpan={2}><strong>Model ID</strong></th>
          <th colSpan={2}><strong>Input price (per 1 million tokens)</strong></th>
          <th><strong>Output price (per 1 million tokens)</strong></th>
        </tr>
        <tr>
          <th>Text/Image/video</th>
          <th>Audio</th>
          <th>Text</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>qwen3.5-omni-plus</td><td>\$1.4</td><td>\$11</td><td>\$8.3</td></tr>
      </tbody>
    </table>
  </Tab>
</Tabs>

## Text generation - Qwen (open source) <span id="t5" />

### Qwen-Coder <span id="t6" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead>
        <tr>
          <th><strong>Model ID</strong></th>
          <th><strong>Deployment scope</strong></th>
          <th><strong>Input tokens per request</strong></th>
          <th><strong>Input price (per 1 million tokens)</strong></th>
          <th><strong>Output price (per 1 million tokens)</strong></th>
        </tr>
      </thead>
      <tbody>
        <tr><td rowSpan={3}>qwen3-coder-480b-a35b-instruct</td><td rowSpan={3}>International</td><td>0</td><td>\$1.5</td><td>\$7.5</td></tr>
        <tr><td>32K</td><td>\$2.7</td><td>\$13.5</td></tr>
        <tr><td>128K</td><td>\$4.5</td><td>\$22.5</td></tr>
      </tbody>
    </table>
  </Tab>
</Tabs>

## Text generation - third-party models <span id="t7" />

### DeepSeek <span id="t8" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead>
        <tr>
          <th><strong>Model ID</strong></th>
          <th><strong>Deployment scope</strong></th>
          <th><strong>Input price (per 1 million tokens)</strong></th>
          <th><strong>Output price (per 1 million tokens)</strong></th>
        </tr>
      </thead>
      <tbody>
        <tr><td>deepseek-v4-flash-0731</td><td>International</td><td>Busy hours: \$0.44 Idle hours: \$0.22</td><td>Busy hours: \$1.32 Idle hours: \$0.66</td></tr>
        <tr><td>deepseek-v4-pro</td><td>International</td><td>\$2.400</td><td>\$4.800</td></tr>
      </tbody>
    </table>
  </Tab>
</Tabs>

## Image generation <span id="t9" />

<Tabs>
  <Tab title="Singapore">
    <table>
      <thead><tr><th><strong>Model ID</strong></th><th><strong>Input price (per 1 million tokens)</strong></th><th><strong>Output price (per 1 million tokens)</strong></th></tr></thead>
      <tbody><tr><td>qwen-image</td><td>\$9</td><td>\$9</td></tr></tbody>
    </table>
  </Tab>
</Tabs>
