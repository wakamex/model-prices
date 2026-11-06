<!-- Copy of https://www.alibabacloud.com/help/en/model-studio/coding-plan.md as served on 2026-11-06. -->


<!DOCTYPE html>
<html lang="en" class="transparent alicloud back-to-top new_default light" traceid="0830559d17940048587908090e">
<link rel="stylesheet" href="//g.alicdn.com/aliyun-help/help-portal-fe/0.12.66/css/index.css" />
<head>
<meta http-equiv="content-type" content="text/html; charset=UTF-8"/>
<meta name="spm-id" content="a2c63">
<meta name="data-spm" content="a2c63" />
<meta name="aplus-core" content="aplus.js">
<meta name="aplus-ajax" content="chksum">
<meta name="aplus-waiting" content="MAN">
<meta name="aplus-pvhash" content="1">
 <!-- MINOR_LANG_ENTRY_GATE：ko/de/vi/th 入口暂关；开放时把码追加到下方 content 并同步 Constants 卡点列表 -->
<meta name="kloud:supported-langs" content="en,zh,tc,ja,id,pt-BR,fr,es,tr"/>

<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="applicable-device" content="pc,mobile">
<meta name="aplus-rhost-v" content="sg.mmstat.com">
<meta name="aplus-rhost-g" content="sg.mmstat.com">
<title>
 Coding plan - Alibaba Cloud Model Studio - Alibaba Cloud Documentation Center

</title>
 <meta name="keywords" content="Model Studio,Coding Plan quota rules,API key generation workflow,Claude Code endpoint setup,free tier request limits,subscription tier comparison">
 <meta name="description" content="Coding plan,Alibaba Cloud Model Studio:Coding Plan gives you access to models including Qwen, GLM, Kimi, and MiniMax in popular AI coding tools. For a fixed monthly fee, it offers a cost-effective alternative to pay-as-you-go API billing.">
 <script>
window.globalData = {
website: "intl",
language: "en",
nodeId:"3005961",
channel: "",
notfound: "",
statusCode: "",
errorType: ""
};
// UT的全局配置变量，在CDN加载前配置
window.$ACE_TRACKER_CONFIG = {
enableHistory: true,
enableHash: false
};
</script>
<!-- <base href="https://www.alibabacloud.com">-->
<link rel="canonical" href="https://www.alibabacloud.com/help/en/model-studio/coding-plan"/>
 <meta property="og:title" content="Coding plan overview - Alibaba Cloud" />
 <meta property="og:type" content="website" />
 <meta property="og:url" content="https://www.alibabacloud.com/help/en/model-studio/coding-plan" />
 <meta property="og:image" content="https://img.alicdn.com/tfs/TB1xpNqnmslXu8jSZFuXXXg7FXa-1200-630.png_.webp" />
 <meta property="og:description" content="Coding plan,Alibaba Cloud Model Studio:Coding Plan gives you access to models including Qwen, GLM, Kimi, and MiniMax in popular AI coding tools. For a fixed monthly fee, it offers a cost-effective alternative to pay-as-you-go API billing." />
 <link rel="shortcut icon" href="//img.alicdn.com/tfs/TB1ugg7M9zqK1RjSZPxXXc4tVXa-32-32.png"/>
<link rel="stylesheet" href="https://o.alicdn.com/fund/alicloud-pure-layout/css/index.min.css" />
 <link
rel="icon"
href="https://img.alicdn.com/imgextra/i2/O1CN01TFs5Qw27uYvfA6gib_!!6000000007857-55-tps-32-32.svg"
type="image/x-icon"
/>
</head>
<body data-spm="" class="HAS_ALPS_RESOURCE"><script>
with(document)with(body)with(insertBefore(createElement("script"),firstChild))setAttribute("exparams","category=&userid=&aplus&yunid=&&trid=0830559d17940048587908090e&asid=AQAAAAB7V+5qXaa0ZgAAAAANI+WN2ey25g==",id="tb-beacon-aplus",src=(location>"https"?"//g":"//g")+".alicdn.com/alilog/mlog/aplus_v2.js")
</script>

 <script async src="https://o.alicdn.com/fund/alicloud-pure-layout/index.js"></script>

<div id="app">
<div class="aliyun-app-layout">

<!-- docId:3005961 -->
<input type="hidden" id="website" value="intl">
<div class="products-wrapper$tip" data-spm="879954">
<section id="products" class="intl-product container">
<div class="row">
<div class="col-lg-3 col-md-3 col-sm-4 col-xs-12" id="navDocument">
<div class="doc-nav">
<a class="doc-center" href="/help/en">
<i class="icon-docs icon-docs-back"></i>
Document Center
</a>
</div>
<div class="placeholder-ele">&nbsp;</div>
</div>
<div class="col-lg-7 col-md-7 col-sm-8 col-xs-12 doc-content">
<div class="all-products action" id="J_AllProducts">
<div class="all-products-head">
<div class="all-products-title">All Products</div>
<div class="all-products-search-wrapper">
<div class="all-products-search focus">
<input autocomplete="off" class="all-products-search-box-input" id="J_AllProductsSearch" placeholder="Search Product" data-spm-anchor-id="a2c4g.11186623.6.i0.1f753945H9RVzu">
<i class="icon-search icon-docs icon-docs-search"></i>
<ul class="all-products-search-result" style="display: none;">
</ul>
</div>
</div>
</div>
<div class="all-products-body" id="J_AllProductsBody"></div>
</div>
<div class="search-product-modal">
Search
</div>
<div class="breadcrumbs-top" data-spm="a1">
<div class="row nav-breadcrumb">
 <div class="col-md-12 hidden-sm hidden-xs">
<ul class="breadcrumb text-sm">
<li><a class="active" title="Document Center" href="/help/en">Document Center</a></li>
 <li><a class="active" title="Alibaba Cloud Model Studio" href="/help/en/model-studio/">Alibaba Cloud Model Studio</a></li>
 <li><a class="active" title="Token Plan" href="/help/en/model-studio/token-plan-user-guide/">Token Plan</a></li>
 <li><a class="active" title="Coding Plan (legacy)" href="/help/en/model-studio/coding-plan-guide/">Coding Plan (legacy)</a></li>
 <li><a class="active" title="Overview" href="/help/en/model-studio/coding-plan">Overview</a></li>
 </ul>
</div>
 <div class="col-md-4 col-sm-12">
<button type="button" class="navbar-toggle bc mr0" data-toggle="collapse"
data-target="#sideMenu-mobile">
<span class="icon-bar"></span>
<span class="icon-bar"></span>
all-products-head <span class="icon-bar"></span>
</button>
</div>
</div>
<form class="search-bar clearfix" method="GET" action="/s/en">
<input type="hidden" name="type" value="doc"/>
<div class="select">
<p class="select-text">
<span class="placeholder">This Product</span>
<i class="icon-docs icon-docs-selected"></i>
</p>
<ul class="select-options" style="display:none;">
<li class="option selected" data-value="h_pid_$productId">This Product</li>
<li class="option" data-value="">All Products</li>
</ul>
<input type="hidden" name="rangeinfo" value="h_pid_2400256"/>
</div>
<input autocomplete="off" class="search-key" type="text" placeholder="Search by keyword" name="k"/>
<ul class="help-top-search-result" style="display: block;"></ul>
<button class="search-submit" type="submit">
<i class="icon-docs icon-docs-search"></i>
</button>
<div class="collapse-menus select">
<p class="select-text">
<span class="placeholder">Alibaba Cloud Model Studio:Coding plan overview</span>
<i class="icon-docs icon-docs-more"></i>
</p>
</div>
</form>
</div>
<header id="header-faq" class="clearfix">
<a class="doc-center" href="/help/en">
<i class="icon-docs icon-docs-back"></i>
Document Center
</a>
<div class="download-links">
 </div>
<h1 class="page-title">Alibaba Cloud Model Studio:Coding plan overview</h1>
<div class="doc-status">
Last Updated:Nov 04, 2026
</div>
</header>
<article class="product-description markdown-body">
<div lang="en" class="icms-help-docs-content">
<link rel="preload" as="image" href="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/9842172771/p1057319.png"/><link rel="preload" as="image" href="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/9842172771/p1057328.png"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/openclaw-color.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/nousresearch.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/claude-color.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/opencode.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cursor.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/codex.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qwen-color.svg"/><link rel="preload" as="image" href="https://cdn.jsdelivr.net/gh/agentscope-ai/QwenPaw@main/website/public/qwenpaw-symbol.png"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cherrystudio-color.svg"/><link rel="preload" as="image" href="https://cdn.jsdelivr.net/gh/chatboxai/chatbox@main/assets/icon.png"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cline.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qoder-color.svg"/><link rel="preload" as="image" href="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/kilocode.svg"/><link rel="preload" as="image" href="https://api.iconify.design/thesvg-color/workbuddy.svg"/><div lang="en" class="icms-help-docs-content"><p data-tag="shortdesc" class="shortdesc">Coding Plan gives you access to models including Qwen, GLM, Kimi, and MiniMax in popular AI coding tools. For a fixed monthly fee, it offers a cost-effective alternative to pay-as-you-go API billing.</p><h2 id="plan-details">Plan details <span id="f514b6df51cks"></span> <span id="f93011b1607v0"></span></h2>
<div class="note note-note"><div class="note-icon-wrapper"></div><div class="note-content"><p><strong>Note</strong></p><ol>
<li>As of March 20, 2026, 00:00:00 (UTC+08:00), the Lite plan is no longer available for new subscriptions (see <a href="https://www.alibabacloud.com/notice/detail?_p_lc=1&amp;id=1781">announcement</a>). As of April 13, 2026, 18:00:00 (UTC+08:00), renewals and upgrades for the Lite plan have been discontinued (see <a href="https://www.alibabacloud.com/notice/detail?_p_lc=1&amp;id=1837">announcement</a>).</li>
<li>The Lite plan supports all plan models, including Qwen, GLM, Kimi, and MiniMax, same as the Pro plan.</li>
</ol></div></div>
<table style="display:table;table-layout:fixed;width:100%;overflow-wrap:anywhere"><colgroup><col style="width:24.99%"/><col style="width:75.01%"/></colgroup><thead><tr><th style="vertical-align:top"><p></p></th><th style="vertical-align:top"><p><strong>Pro</strong></p></th></tr></thead><tbody><tr><td style="vertical-align:top"><p>Supported models</p></td><td style="vertical-align:top"><p>Only the following exact model versions are supported:</p> <p>Recommended models: <strong>qwen3.7-plus</strong> (vision), <strong>qwen3.6-plus</strong> (vision), <strong>kimi-k2.5</strong> (vision), <strong>glm-5</strong>, and <strong>MiniMax-M2.5</strong></p> <p>More models: <code>qwen3.5-plus</code> (vision)</p> <p>Models not listed above are not supported.</p></td></tr><tr><td style="vertical-align:top"><p>Price</p></td><td style="vertical-align:top"><p><strong>$ 50</strong>/month</p></td></tr><tr><td style="vertical-align:top"><p>Quota</p></td><td style="vertical-align:top"><ul><li><p>Up to <strong>6,000</strong> requests per 5 hours</p></li> <li><p>Up to <strong>45,000</strong> requests per week</p></li> <li><p>Up to <strong>90,000</strong> requests per month</p></li></ul></td></tr></tbody></table>
<ul>
<li>
<p><strong>Limited availability</strong>: Slots are limited and available on a first-come, first-served basis. New slots are restocked daily at 00:00:00 (UTC+08:00). Go to the <a href="https://common-buy-intl.alibabacloud.com/coding-plan/">Coding Plan purchase page</a> to subscribe.</p>
</li>
<li>
<p><strong>Quota consumption:</strong> Each query consumes quota based on the number of model calls. Simple tasks typically use 5–10 calls, while complex tasks may use 10–30 or more. Actual consumption varies by task complexity, context, and tool usage. Check your usage on the <a href="https://modelstudio.console.alibabacloud.com/ap-southeast-1/subscription/coding-plan">Coding Plan page</a>. The three limits above apply simultaneously as caps, and whichever is reached first takes effect. When any limit is reached, calls are paused. The limits are not cumulative and do not represent a guaranteed capacity distributed evenly over time.</p>
</li>
<li>
<p><strong>Quota replenishment</strong>:</p>
<ol>
<li>5-hour quota: Rolls over automatically, releasing usage from 5 hours ago each minute. For example, if you use 100 calls at 10:00, the 100 calls are restored at 15:00. If you use 50 calls at 10:30, the 50 calls are restored at 15:30.</li>
<li>Weekly quota: Resets every Monday at 00:00:00 (UTC+08:00).</li>
<li>Monthly quota: Resets at 00:00:00 (UTC+08:00) on your subscription renewal date each month.</li>
</ol>
</li>
</ul>
<h2 id="quick-start">Quick start <span id="5ebfd53ae8b1q"></span> <span id="06012909b1l5q"></span></h2>
<h3 id="step-1-subscribe-to-a-coding-plan">Step 1: Subscribe to a Coding Plan <span id="d8bfda628cox3"></span> <span id="40184273b7pog"></span></h3>
<p>Go to the <a href="https://common-buy-intl.alibabacloud.com/coding-plan/">Coding Plan purchase page</a>, select a plan, and complete the subscription.</p>
<p>Subscribe directly with your Alibaba Cloud account. If you are a RAM user, your Alibaba Cloud account owner must grant you the necessary permissions before you can subscribe.</p>
<section class="collapse" id="accordion-authorize-a-ram-user"><p>Authorize a RAM user</p><div><ol>
<li><strong>Add a user:</strong> Log on to Alibaba Cloud Model Studio with your Alibaba Cloud account. Go to the <a href="https://modelstudio.console.alibabacloud.com/ap-southeast-1/model/settings/permission">Permissions</a> page of your target workspace. Click <strong>Add User</strong>, specify a username for the RAM user, and click <strong>Confirm</strong>.<img class="image break" src="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/9842172771/p1057319.png" alt="image" width="700"/></li>
<li><strong>Grant permissions:</strong> Find the user and click <strong>Permissions</strong> in the Actions column. Select the <strong>Administrator</strong> role and click <strong>Confirm</strong> to complete the authorization.<img class="image break" src="https://help-static-aliyun-doc.aliyuncs.com/assets/img/en-US/9842172771/p1057328.png" alt="image" width="600"/></li>
</ol></div></section>
<h3 id="step-2-get-plan-specific-api-key-and-base-url">Step 2: Get plan-specific API key and base URL <span id="2531c37fd64f9"></span> <span id="2782cf93b1w8h"></span></h3>
<p>You must use the plan-specific API key and base URL to ensure usage is correctly deducted from your plan&#x27;s quota.</p>
<ul>
<li>
<p><strong>API key</strong>: On the <a href="https://modelstudio.console.alibabacloud.com/ap-southeast-1/subscription/coding-plan">Coding Plan page</a>, get your Coding Plan-specific API key (in the format <code>sk-sp-xxxxx</code>).</p>
</li>
<li>
<p><strong>Base URL</strong>: Configure one of the following base URLs in your AI tool. The URL depends on the tool. See your tool&#x27;s documentation for details.</p>
<ul>
<li><strong>OpenAI-compatible protocol</strong>: <code>https://coding-intl.dashscope.aliyuncs.com/v1</code></li>
<li><strong>Anthropic-compatible protocol</strong>: <code>https://coding-intl.dashscope.aliyuncs.com/apps/anthropic</code></li>
</ul>
</li>
</ul>
<div class="note note-note"><div class="note-icon-wrapper"></div><div class="note-content"><p><strong>Note</strong>Which endpoint to use:</p><ul>
<li><strong>Pay-as-you-go</strong>: Use your general Model Studio API key (in the format <code>sk-xxxxx</code>) with the base URL <code>https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/xxxxxx</code> (OpenAI-compatible mode).</li>
<li><strong>Coding Plan quota deduction</strong>: Use your Coding Plan API key (in the format <code>sk-sp-xxxxx</code>) with the base URL <code>https://coding-intl.dashscope.aliyuncs.com/v1</code>.</li>
</ul><p>The two sets of API keys and base URLs are not interchangeable. Do not mix them.</p></div></div>
<h3 id="step-3-integrate-with-an-ai-tool">Step 3: Integrate with an AI tool <span id="5f8507878alf8"></span> <span id="d976677d45eer"></span></h3>
<table bordertype="no-border" style="display:table;table-layout:fixed;width:100%;overflow-wrap:anywhere"><colgroup><col style="width:33.33%"/><col style="width:33.33%"/><col style="width:33.34%"/></colgroup><tbody><tr><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/openclaw-color.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/openclaw">OpenClaw</a></strong><p>Open-source, self-hosted personal AI assistant</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/nousresearch.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/hermes-agent">Hermes Agent</a></strong><p>Open-source AI agent framework with built-in self-learning loop</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/claude-color.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/claude-code">Claude Code</a></strong><p>AI terminal coding assistant that supports natural language programming</p></td></tr><tr><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/opencode.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/opencode">OpenCode</a></strong><p>Open-source AI programming agent tool</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cursor.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/cursor">Cursor</a></strong><p>AI-native code editor</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/codex.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/codex">Codex</a></strong><p>Command-line programming tool from OpenAI</p></td></tr><tr><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qwen-color.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/qwen-code">Qwen Code</a></strong><p>Open-source CLI coding tool</p></td><td style="vertical-align:top"><img class="image inline" src="https://cdn.jsdelivr.net/gh/agentscope-ai/QwenPaw@main/website/public/qwenpaw-symbol.png" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/qwenpaw">QwenPaw</a></strong><p>Open-source personal AI assistant with local and cloud deployment</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cherrystudio-color.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/cherry-studio">Cherry Studio</a></strong><p>Multi-model desktop client</p></td></tr><tr><td style="vertical-align:top"><img class="image inline" src="https://cdn.jsdelivr.net/gh/chatboxai/chatbox@main/assets/icon.png" alt="" width="28" height="28"/><strong><a href="https://www.alibabacloud.com/help/model-studio/cline-tool">Chatbox</a></strong><p>Cross-platform AI desktop client</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/cline.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/cline">Cline</a></strong><p>VS Code extension for intelligent code completion and debugging</p></td><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/qoder-color.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/qoder-agent">Qoder</a></strong><p>Agentic coding platform for real-world software development</p></td></tr><tr><td style="vertical-align:top"><img class="image inline" src="https://unpkg.com/@lobehub/icons-static-svg@latest/icons/kilocode.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/kilo-cli">Kilo CLI</a></strong><p>Lightweight, high-performance command-line programming tool</p></td><td style="vertical-align:top"><img class="image inline" src="https://api.iconify.design/thesvg-color/workbuddy.svg" alt="" width="28" height="28"/><strong><a href="/help/en/model-studio/workbuddy">WorkBuddy</a></strong><p>Desktop AI agent workbench</p></td></tr><tr><td style="vertical-align:top"><strong><a href="/help/en/model-studio/more-tools">More tools</a></strong><p>Other programming tools</p></td></tr></tbody></table>
<h2 id="before-you-subscribe">Before you subscribe <span id="d489c2bd21rap"></span> <span id="d79db9c14dbmq"></span></h2>
<p>The Coding Plan service is <strong>non-refundable</strong>. Before you subscribe, note the following:</p>
<ol>
<li><strong>Prohibition of API calls</strong>: This plan is for interactive use in programming tools such as Claude Code, Qoder and OpenClaw. Do not use the plan&#x27;s API key for automated scripts, application backends, or other non-interactive scenarios. <strong>Using the API key outside the permitted scope is a violation that may result in subscription suspension or API key revocation.</strong></li>
<li><strong>Account usage policy</strong>: The plan is for your use only and must not be shared. Account sharing may lead to restrictions on your subscription.</li>
<li><strong>Rate limits and resource scheduling</strong>: To ensure fair use for all users, in addition to the quota limits above, this service enforces technical limits on the number of concurrent requests and the request rate per account. When overall platform load is high, or when a single account consumes an unusually concentrated amount of resources within a short period, we may temporarily queue, throttle, or briefly interrupt requests from that account. Such adjustments are typically lifted automatically within minutes to hours. These adjustments are standard technical safeguards and are not considered a service interruption or a breach of contract. The specific thresholds are part of platform security and stability policies and may be adjusted dynamically based on operating conditions.</li>
</ol>
<h2 id="faq">FAQ <span id="50095a467eg3p"></span> <span id="437dc15afa03b"></span></h2>
<h3 id="unexpected-charges-with-a-coding-plan">Unexpected charges with a Coding Plan <span id="db649df68086n"></span> <span id="bf4ad0346fdpk"></span></h3>
<p>This happens when you use the general Model Studio API key and base URL instead of your Coding Plan-specific ones. This usage is billed on a pay-as-you-go basis, resulting in extra charges. To resolve this, switch to your Coding Plan API key (starting with <code>sk-sp-</code>) and base URL (containing <code>coding-intl.dashscope.aliyuncs.com</code>). See <a href="/help/en/model-studio/coding-plan#2531c37fd64f9">Get your plan-specific API key and base URL</a>. To stop pay-as-you-go billing, go to the <strong>API Key management</strong> page in the Model Studio console and delete the general API key (starting with <code>sk-</code>), keeping only your Coding Plan API key. Subsequent calls are then deducted from your plan quota only and no longer incur pay-as-you-go charges.</p>
<h3 id="why-is-the-lite-plan-no-longer-available-for-new-subscriptions">Why is the Lite plan no longer available for new subscriptions? <span id="b2c3d4e5f6g7h"></span> <span id="a1b2c3d4e5f6h"></span></h3>
<p>Due to a product upgrade, the Coding Plan Lite plan stopped accepting new orders on March 20, 2026 (see <a href="https://www.alibabacloud.com/en/notice/detail?id=1781">discontinuation announcement</a>), and renewals and upgrades were discontinued on April 13, 2026 (see <a href="https://www.alibabacloud.com/en/notice/detail?id=1837">renewal discontinuation announcement</a>). Existing subscribers can continue using the service until it expires.</p>
<h3 id="are-existing-lite-plan-subscribers-affected">Are existing Lite plan subscribers affected? <span id="f6g7h8i9j0k1l"></span> <span id="e5f6g7h8i9j0k"></span></h3>
<p>Existing Coding Plan Lite subscribers can continue using the service until it expires. Renewals and upgrades for the Lite plan were discontinued on April 13, 2026. To continue using Coding Plan, subscribe to the Pro plan.</p>
<p>For more questions, refer to the <a href="/help/en/model-studio/coding-plan-faq">FAQ</a>.</p></div>
</div>
</article>
<script type="text/javascript">
window.storeDocs = {
language: '$lang',
docGithubLink: '$!githubInfo.url'
}
</script>
<div class="nav-footer">
 </div>
<div class="alicloud-document-ask clearfix"></div>
<div class="feedback-message" style="display:none;">
<span class="hasfeedback acon acon-done-16"></span>
Thank you! We've received your  feedback.
</div>
</div>
<div class="col-log-2 col-md-2 col-sm-0 col-xs-0 nav-catalog">
<div class="article-catalog" id="articleCatalog"></div>
</div>
</div>
</section>
</div>
</div>
</div>
<script
crossorigin
src="https://g.alicdn.com/code/lib/??react/16.8.6/umd/react.production.min.js,react-dom/16.8.6/umd/react-dom.production.min.js"
></script>
<script
src="https://g.alicdn.com/code/lib/lodash.js/4.17.21/lodash.min.js"
crossorigin="anonymous"
></script>
<script src="//g.alicdn.com/aliyun-help/help-portal-fe/0.12.66/js/vendor.js"></script>
<script src="//g.alicdn.com/aliyun-help/help-portal-fe/0.12.66/js/index.js"></script>
<script defer src="https://cloud-assets.alicdn.com/alicdn/dawn/user-tracker/latest/js/index.js"></script>
</body>
</html>