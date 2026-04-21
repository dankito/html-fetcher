## The Hard Truth About DataDome

That response is a **DataDome CAPTCHA challenge** — and there's no clean programmatic way to solve it automatically. Here's why:

DataDome's challenge at this tier works like this:
1. It loads a JS script from `ct.captcha-delivery.com/c.js`
2. That script runs **hundreds of browser behaviour probes** — mouse movement history, timing entropy, canvas fingerprint, AudioContext fingerprint, iframe sandboxing behaviour, WebRTC, font enumeration, etc.
3. It sends the result to `geo.captcha-delivery.com` and only if the score passes does it set a valid `datadome` cookie and redirect back
4. The iframe has `sandbox="allow-scripts allow-same-origin allow-forms"` — no `allow-top-navigation`, so it can't even redirect itself out

**What "resolving it like a real browser" would require:**
- A real GPU (not SwiftShader) for canvas/WebGL fingerprinting ✗ (headless)
- Real historical mouse movement patterns ✗ (no user interaction)
- A non-datacenter IP with clean reputation — **this is likely the main blocker**
- Passing the AudioContext fingerprint check ✗ (headless has no audio)

Even `undetected-chromedriver` and paid stealth services often fail on DataDome tier-2 challenges. The `datadome` cookie in the original browser headers you shared is the solved token — DataDome issued it to your real browser after passing all checks.

**The only practical approaches:**

| Approach | Realistic? |
|---|---|
| Solve programmatically in headless browser | No — GPU/audio/IP checks block it |
| Reuse a valid `datadome` cookie from a real browser session | Yes, but it expires and is IP-bound |
| Residential proxy with clean IP reputation | Partially — removes IP block, but JS checks remain |
| Paid CAPTCHA-solving service (2captcha, CapSolver) | Yes — they have humans/specialized solvers for DataDome |
| Scraping API (ScrapingBee, Zyte, BrightData) | Yes — purpose-built, handles DataDome natively |

---

## For DataDome specifically — your real options

**Option A: Cookie passthrough (quick & dirty)**
Add an optional `cookies` parameter to `FetchRequest`. The user provides the `datadome` cookie harvested from a real browser session. curl_cffi sends it along and the site treats it as a returning verified user. Expires after ~24h and is IP-bound, but works.

**Option B: CapSolver / 2captcha**
Both have DataDome-specific solvers. You'd call their API with the challenge parameters extracted from that iframe URL, get back a valid `datadome` cookie, then retry the actual page fetch. Costs ~$1–3 per 1000 solves.

**Option C: Zyte API / BrightData**
Drop-in scraping APIs that handle DataDome, Cloudflare, etc. transparently. You just send them the URL and get back clean HTML. Most expensive but zero maintenance.

For a general-purpose fetcher, Option A as an escape hatch + Option C for known-blocked domains is the pragmatic production architecture.