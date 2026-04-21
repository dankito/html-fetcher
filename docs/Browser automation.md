Here's a comprehensive overview as of 2026:

---

## How they all work (general principle)

All of these tools launch or connect to a real browser process (Chromium, Firefox, or WebKit) and control it via a protocol — either **CDP** (Chrome DevTools Protocol), **WebDriver/W3C**, or direct OS-level input. The browser actually runs and executes JavaScript, which is the whole point. The key differentiator between tools is **how detectable the automation is**.

Detection vectors anti-bot systems look for:
- `navigator.webdriver = true`
- Missing browser plugins/APIs (e.g. no `chrome.app`)
- CDP-specific properties leaking into the page JS environment
- Inconsistent TLS fingerprints (unrelated to browser content, but still)
- Behavioral signals (instant mouse movements, no scroll, instant clicks)
- Headless-specific User-Agent strings

---

## The tools

### 1. Playwright (Microsoft)
**Languages:** JS/TS, Python, Java, .NET  
**Local use:** Library install; Docker via `mcr.microsoft.com/playwright`  
**Browsers:** Chromium, Firefox, WebKit  
**How it works:** Connects directly to the browser's automation endpoints like CDP. Supports browser contexts — lightweight isolated sessions that behave like independent browser profiles.  
**Process lifecycle:** Browser stays running between pages; you explicitly close it.  
**Resources:** ~300–500 MB RAM per Chromium instance at idle; CPU near 0% idle, spikes to 50–100% during page load.  
**Bot detection:** ❌ Bad out of the box. Headless browsers leak signals like `navigator.webdriver`, missing plugins, and the `HeadlessChrome` User-Agent marker that anti-bot systems instantly detect. Needs stealth plugins (see below).  
**Pros:** Best-in-class API, auto-wait, widest language support, very actively maintained.  
**Cons:** Detected by Cloudflare/DataDome/Akamai without additional stealth work.

---

### 2. Playwright + playwright-stealth / playwright-extra
**Languages:** Python, JS  
**Local use:** pip/npm plugin on top of Playwright  
**How it works:** Injects JS patches before page scripts run to fake missing APIs, override `navigator.webdriver`, spoof plugins, etc.  
**Bot detection:** ⚠️ Medium. The Python package is actively maintained and works well against basic fingerprint checks. The Node.js packages last released in March 2023 and haven't received new evasion modules since, so they lag behind newer anti-bot techniques. Stealth plugins alone usually cannot bypass Cloudflare, which uses TLS fingerprinting, cryptographic challenges, and server-side behavioral analysis that operate below where stealth plugins can intervene.  
**Cons:** JS patches are themselves detectable — anti-bot systems can find the patch artifacts.

---

### 3. Patchright
**Languages:** Python (primary), JS  
**Local use:** pip library, drop-in Playwright replacement  
**How it works:** A patched fork of Playwright's Chromium that removes CDP leaks at the browser-binary level rather than patching them via JS.  
**Process lifecycle:** Same as Playwright.  
**Resources:** Comparable to Playwright (~300–500 MB RAM idle).  
**Bot detection:** ⭐⭐⭐⭐ Good. Fixes the CDP-level detection vectors that JS patches can't reach. Patchright solved a real problem by fixing Playwright's CDP leaks. Struggles with interactive Cloudflare Turnstile in headless mode.  
**Cons:** Chrome-only, mostly Python, requires persistent browser context (can't use `launch()` without a profile).

---

### 4. Camoufox
**Languages:** Python (primary; Playwright-compatible API)  
**Local use:** pip library + fetches its own Firefox binary  
**How it works:** Modifies Firefox at the C++ level rather than applying JavaScript patches. Canvas fingerprints, WebGL renderers, font enumeration, screen dimensions, and navigator properties are all rewritten internally.  
**Process lifecycle:** Browser keeps running; you manage context lifetime.  
**Resources:** ~300–500 MB RAM idle. When Camoufox is idle, it can use almost twice as much CPU as Playwright Firefox in headed mode. In headless mode this is more manageable.  
**Bot detection:** ⭐⭐⭐⭐⭐ Currently the best open-source option. Using Camoufox, the headless and stealth scores on CreepJS were 0%, with both headless and virtual display modes. It's the only tool that consistently achieves 0% detection scores across major test suites.  
**Cons:** Firefox only (some sites serve different content to Firefox). Camoufox went through a year-long maintenance gap; development resumed in late 2025/early 2026 but the project is still recovering — expect some instability. Not natively available for Java/Go.

---

### 5. Nodriver
**Languages:** Python only  
**Local use:** pip library, uses system Chrome  
**How it works:** A "CDP-minimal" framework — abandons traditional automation protocols and instead communicates with Chrome directly while avoiding the detection vectors that traditional tools create. No WebDriver, no CDP fingerprint leaks.  
**Process lifecycle:** Chrome starts and stays running; async API.  
**Resources:** Comparable to a bare Chrome instance (~300–450 MB idle). Known memory leak issues under long-running workloads.  
**Bot detection:** ⭐⭐⭐⭐ Very good against most systems. Nodriver avoids detection vectors entirely rather than patching them. Less consistent than Camoufox against the most sophisticated systems.  
**Cons:** Python only. Only supports SOCKS5 proxies. No Java/Go support. Created by the same author as `undetected-chromedriver` which had stability/maintenance issues.

---

### 6. SeleniumBase (UC Mode)
**Languages:** Python (primary), Java via base Selenium  
**Local use:** pip library  
**How it works:** Wraps Selenium + `undetected-chromedriver` with a higher-level API. UC Mode patches ChromeDriver to remove automation fingerprints.  
**Process lifecycle:** Browser stays open between calls; close explicitly.  
**Resources:** ~350–550 MB RAM idle (includes ChromeDriver process).  
**Bot detection:** ⭐⭐⭐ Medium-good. Better than plain Selenium, worse than Camoufox/Patchright. For simplicity with existing Selenium code, SeleniumBase UC Mode strikes a good balance.  
**Cons:** Slower than Playwright-based tools due to WebDriver protocol overhead. Selenium's HTTP polling adds latency.

---

### 7. Selenium (plain)
**Languages:** Java, Python, JS, C#, Ruby, Go  
**Local use:** Library + separate driver binary (chromedriver etc.)  
**How it works:** Uses the W3C WebDriver protocol — a driver binary sits between your code and the browser, introducing inherent latency.  
**Process lifecycle:** Browser and driver both run; close explicitly.  
**Resources:** ~350–600 MB RAM idle (browser + driver).  
**Bot detection:** ❌ Terrible. Sets `navigator.webdriver = true`, easiest to detect of all options.  
**Pros:** Broadest language support including Java. Mature ecosystem.  
**Cons:** Detected immediately by any serious anti-bot system. Slowest execution. Selenium is typically slowest due to HTTP polling.

---

### 8. Puppeteer + puppeteer-extra-stealth
**Languages:** JS/TS only  
**Local use:** npm library, downloads its own Chromium  
**How it works:** CDP-based like Playwright, with a stealth plugin adding JS patches.  
**Process lifecycle:** Stays running; close explicitly.  
**Resources:** ~300–500 MB RAM idle.  
**Bot detection:** ⭐⭐⭐ Medium. CreepJS detects a regular Puppeteer setup as 100% headless, while with the puppeteer-extra-stealth-plugin, it's possible to bring it down to 33%.  
**Cons:** JS/TS only. No Java/Go. Node.js stealth plugin is unmaintained since 2023.

---

### 9. Browserless (self-hosted)
**Languages:** Any via WebSocket/CDP; official SDKs for JS, Python  
**Local use:** Docker (`ghcr.io/browserless/chrome`)  
**How it works:** Runs headless browsers as a managed service locally. You connect existing Playwright, Puppeteer, or Selenium code to remote browsers over WebSocket, or call REST/GraphQL APIs for screenshots, PDFs, scraping.  
**Process lifecycle:** Self-serve cloud and Enterprise offerings include BrowserQL for avoiding detectors and solving CAPTCHAs. The container keeps running as a server; browser sessions are created/destroyed per request.  
**Resources:** The container itself is lightweight; each spawned browser ~300–500 MB RAM. Can pool sessions.  
**Bot detection:** ⭐⭐⭐ Medium (base). BrowserQL with stealth mode adds human-like behavior. SSPL license — commercial use requires purchasing a license.  
**Pros:** Language-agnostic (any language that speaks HTTP/WebSocket). Connection pooling, queue management, debugging UI. Good for running from Java or Go.  
**Cons:** SSPL license is restrictive for commercial use. Stealth features are mostly in the paid tier.

---

### 10. Zenika/alpine-chrome (Docker)
**Languages:** Any via CDP WebSocket  
**Local use:** Docker  
**How it works:** Minimal Alpine Linux Docker image with Chrome pre-installed, configured with the necessary flags for headless operation in containers. You connect Puppeteer/Playwright to it via CDP.  
**Process lifecycle:** Container runs persistently; Chrome stays running.  
**Resources:** Very lean image (~300 MB image size). At idle, Chrome ~300–400 MB RAM.  
**Bot detection:** ❌ Bare Chrome — same as plain Playwright/Puppeteer without stealth. No stealth built-in.  
**Pros:** Extremely simple, lightweight, no licensing concerns, great for CI.  
**Cons:** No stealth at all. Just a convenient way to run Chrome in Docker.

---

## Summary table

| Tool | Languages | Stealth quality | Process after use | Idle RAM | Docker-friendly |
|---|---|---|---|---|---|
| Playwright (bare) | JS, Python, Java, .NET | ❌ | Keeps running | ~350 MB | ✅ |
| Playwright + stealth | JS, Python | ⚠️ Medium | Keeps running | ~350 MB | ✅ |
| Patchright | Python | ⭐⭐⭐⭐ | Keeps running | ~400 MB | ✅ |
| **Camoufox** | Python | ⭐⭐⭐⭐⭐ | Keeps running | ~400 MB | ✅ |
| Nodriver | Python | ⭐⭐⭐⭐ | Keeps running | ~350 MB | ✅ |
| SeleniumBase UC | Python | ⭐⭐⭐ | Keeps running | ~450 MB | ✅ |
| Selenium (plain) | Java, Python, JS, Go... | ❌ | Keeps running | ~500 MB | ✅ |
| Puppeteer + stealth | JS only | ⭐⭐⭐ | Keeps running | ~400 MB | ✅ |
| Browserless (self-hosted) | Any (HTTP/WS) | ⭐⭐⭐ | Server persists | ~400 MB/session | ✅✅ |
| zenika/alpine-chrome | Any (CDP) | ❌ | Container persists | ~350 MB | ✅✅ |

**Important notes:**
- None of these tools stop the browser process automatically after a single fetch — they all keep the browser running until you explicitly close it. This is by design for performance (cold start for a browser is 1–3 seconds).
- For Java and Go, your best local options are **Selenium** (poor stealth) or **Browserless via WebSocket** (good API, mediocre stealth without paid tier). For maximum stealth from Java/Go, the realistic approach is running Camoufox as a subprocess/sidecar via Python and communicating over HTTP, or using Browserless self-hosted with its REST API.
- Cloudflare's most aggressive modes (JS challenge + Turnstile) still defeat even the best of these tools under headless conditions without residential proxies. The proxy matters almost as much as the tool itself.