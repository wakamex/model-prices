# Coding plan overview

> Coding Plan gives you access to models including Qwen, GLM, Kimi, and MiniMax in popular AI coding tools. For a fixed monthly fee, it offers a cost-effective alternative to pay-as-you-go API billing.

## Plan details <span id="f514b6df51cks" />

<Note>
  1. The Lite plan stopped accepting new purchases as of 00:00:00, March 20, 2026 (UTC+08:00) (see the [announcement](https://www.alibabacloud.com/en/notice/detail?_p_lc=1\&id=1781)); renewals and upgrades stopped as of 18:00:00, April 13 (UTC+08:00) (see the [announcement](https://www.alibabacloud.com/en/notice/detail?_p_lc=1\&id=1837)).
  2. The Lite plan supports all plan models (including Qwen, GLM, Kimi, and MiniMax), same as the Pro plan.
</Note>

<table style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}><colgroup><col style={{ width: "24.99%" }} /><col style={{ width: "75.01%" }} /></colgroup><thead><tr><th style={{ verticalAlign: "top" }} /><th style={{ verticalAlign: "top" }}><p><strong>Pro Plan</strong></p></th></tr></thead><tbody><tr><td style={{ verticalAlign: "top" }}><p>Supported models</p></td><td style={{ verticalAlign: "top" }}><p>Featured Models: <strong>qwen3.7-plus</strong> (supports image understanding), <strong>qwen3.6-plus</strong> (supports image understanding), <strong>kimi-k2.5</strong> (supports image understanding), <strong>glm-5</strong>, <strong>MiniMax-M2.5</strong></p> <p>More Models: qwen3.5-plus (supports image understanding)</p> <p>Models not listed above are not supported.</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Pricing</p></td><td style={{ verticalAlign: "top" }}><p><strong>\$ 50</strong>/Month(s)</p></td></tr><tr><td style={{ verticalAlign: "top" }}><p>Usage limits</p></td><td style={{ verticalAlign: "top" }}><ul><li><p><strong>6,000</strong> requests every 5 hours</p></li> <li><p><strong>45,000</strong> requests per week</p></li> <li><p><strong>90,000</strong> requests per month</p></li></ul></td></tr></tbody></table>

- <strong>Limited-time offer</strong>: Limited quota, first come, first served. Quotas are replenished daily at 00:00:00 (UTC+08:00); go to the [Coding Plan purchase page](https://common-buy-intl.alibabacloud.com/coding-plan/) to grab one.
- <strong>Quota consumption:</strong> Each prompt deducts quota based on the actual number of "model calls". A simple task consumes about 5-10 calls, and a complex task about 10-30+ calls; actual consumption depends on task difficulty, context, and tool usage. You can view usage on the [Coding Plan page](https://modelstudio.console.alibabacloud.com/ap-southeast-1/subscription/coding-plan).
- <strong>Quota recovery</strong>:

  1. 5-hour quota: rolling recovery — quota consumed 5 hours earlier is automatically released every minute. Example: 100 calls used at 10:00 → 100 calls restored at 15:00; 50 calls used at 10:30 → 50 calls restored at 15:30.
  2. Weekly quota: resets every Monday at 00:00:00 (UTC+08:00).
  3. Monthly quota: resets at 00:00:00 (UTC+08:00) on the subscription day of the next month.

## QuickStart <span id="5ebfd53ae8b1q" />

### Step 1: Subscribe to the Coding Plan <span id="d8bfda628cox3" />

Go to the [Coding Plan purchase page](https://common-buy-intl.alibabacloud.com/coding-plan/) to select and purchase a plan based on your actual needs.

The primary account can subscribe to the service directly. RAM sub-accounts must complete the following authorization steps before subscribing.

<Accordion title="Steps to authorize a RAM sub-account">
  1. Log on with the primary account, open [**Permission management**](https://modelstudio.console.alibabacloud.com/ap-southeast-1/model/settings/permission), and confirm the current workspace. Click **Add user**, select the target RAM user, enter the username, and then click **OK**. <Image src="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/4734072771/p1057319.png" alt="image" width={700} />
  2. <strong>Grant permissions:</strong>Click <strong>Permission management</strong> on the right of the user, add the <strong>administrator</strong> permission, and then click <strong>OK</strong> to complete the authorization.<Image src="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/4734072771/p1057328.png" alt="image" width={600} />
</Accordion>

### Step 2: Obtain the plan API Key and Base URL <span id="2531c37fd64f9" />

You must obtain and configure the API Key and Base URL of the plan before you can use the plan correctly and have its quota deducted.

- <strong>API Key</strong>: On the [Coding Plan page](https://modelstudio.console.alibabacloud.com/ap-southeast-1/subscription/coding-plan), obtain the Coding Plan API Key (in the format `sk-sp-xxxxx`).
- <strong>Base URL</strong>: You then need to configure one of the following Base URLs in your AI tool (this varies by tool). For specific steps, see the documentation of the corresponding AI tool.

  - <strong>OpenAI-compatible protocol</strong>: `https://coding-intl.dashscope.aliyuncs.com/v1`
  - <strong>Anthropic-compatible protocol</strong>: `https://coding-intl.dashscope.aliyuncs.com/apps/anthropic`

<Note>
  The Coding Plan API Key and Base URL are not interchangeable with the pay-as-you-go Model Studio API Key (`sk-xxxxx`) and Base URL (`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/xxxxxx`); do not mix them up.
</Note>

### Step 3: Connect an AI tool <span id="5f8507878alf8" />

<table bordertype="no-border" style={{ display: "table", tableLayout: "fixed", width: "100%", overflowWrap: "anywhere" }}>
  <colgroup>
    <col style={{ width: "33.33%" }} />

    <col style={{ width: "33.33%" }} />

    <col style={{ width: "33.34%" }} />
  </colgroup>

  <tbody>
    <tr>
      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/openclaw-color.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/openclaw">OpenClaw</a></strong>

        Open-source, self-hosted personal AI assistant
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/nousresearch.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/hermes-agent">Hermes Agent</a></strong>

        Open-source AI agent framework with a built-in self-learning loop
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/claude-color.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/claude-code">Claude Code</a></strong>

        Terminal AI coding assistant that supports natural language programming
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/opencode.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/opencode">OpenCode</a></strong>

        Open-source AI coding agent tool
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cursor.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/cursor">Cursor</a></strong>

        AI-native code editor
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/codex.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/codex">Codex</a></strong>

        Command-line coding tool released by OpenAI
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qwen-color.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/qwen-code">Qwen Code</a></strong>

        Open-source command-line AI coding tool
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://cdn.jsdelivr.net/gh/agentscope-ai/QwenPaw@main/website/public/qwenpaw-symbol.png" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/qwenpaw">QwenPaw</a></strong>

        Open-source personal AI assistant that supports both local and cloud deployment
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cherrystudio-color.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/cherry-studio">Cherry Studio</a></strong>

        Multi-model desktop client
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <Image src="https://cdn.jsdelivr.net/gh/chatboxai/chatbox@main/assets/icon.png" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="https://www.alibabacloud.com/help/model-studio/cline-tool">Chatbox</a></strong>

        Cross-platform AI desktop client
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cline.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/cline">Cline</a></strong>

        VS Code extension with intelligent code completion and debugging
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qoder-color.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/qoder-agent">Qoder</a></strong>

        Agentic coding platform for real-world software development
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <Image src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/kilocode.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/kilo-cli">Kilo CLI</a></strong>

        Lightweight, high-performance command-line coding tool
      </td>

      <td style={{ verticalAlign: "top" }}>
        <Image src="https://api.iconify.design/thesvg-color/workbuddy.svg" alt="" className="inline" noZoom width={28} height={28} /> <strong><a href="/help/en/model-studio/workbuddy">WorkBuddy</a></strong>

        Desktop AI Agent Dashboard
      </td>
    </tr>

    <tr>
      <td style={{ verticalAlign: "top" }}>
        <strong><a href="/help/en/model-studio/more-tools">More tools</a></strong>

        Other coding tools
      </td>
    </tr>
  </tbody>
</table>

### Step 4: Get Started <span id="h8k6l4m2n1o3p" />

After the configuration is complete, start a conversation in your selected coding tool.

## Before you subscribe <span id="d489c2bd21rap" />

The Coding Plan service is <strong>non-refundable</strong>. Therefore, please be aware of the following important information before subscribing:

1. <strong>API calls are strictly prohibited</strong>: The plan can only be used in coding tools (such as Claude Code, Qoder, OpenClaw, and more). Using API calls for automated scripts, custom application backends, or any non-interactive batch call scenarios is prohibited. <strong>Using the plan API Key for calls beyond the permitted scope will be considered a violation or abuse, and may result in suspension of the subscription or blocking of the API Key.</strong>
2. <strong>Account usage rules</strong>: The plan is for the exclusive use of the subscriber, and sharing is prohibited. Sharing your account may restrict your subscription benefits.

## FAQ <span id="50095a467eg3p" />

### Why is an overdue balance or charge still shown after I have purchased a Coding Plan? <span id="db649df68086n" />

You have used the Model Studio general API Key and Base URL by mistake, so the system identifies the usage as pay-as-you-go billing, resulting in additional charges. Please switch to the Coding Plan API Key (starting with `sk-sp-`) and the plan Base URL (containing `coding-intl.dashscope.aliyuncs.com`). For configuration instructions, see [Obtain the plan API Key and Base URL](/help/en/model-studio/coding-plan#2531c37fd64f9).

### Why has new purchase of the Lite plan been discontinued? <span id="b2c3d4e5f6g7h" />

Due to a product upgrade, the Coding Plan Lite plan stopped accepting new orders on March 20, 2026 (see [discontinuation announcement](https://www.alibabacloud.com/en/notice/detail?id=1781)), and renewals and upgrades were discontinued on April 13, 2026 (see [renewal discontinuation announcement](https://www.alibabacloud.com/en/notice/detail?id=1837)). Existing subscribers can continue using the service until it expires.

### Are the benefits of users who have purchased the Lite plan affected? <span id="f6g7h8i9j0k1l" />

Existing Coding Plan Lite subscribers can continue using the service until it expires. Renewals and upgrades for the Lite plan were discontinued on April 13, 2026. To continue using Coding Plan, subscribe to the Pro plan.

For more questions, refer to the [FAQ](/help/en/model-studio/coding-plan-faq).