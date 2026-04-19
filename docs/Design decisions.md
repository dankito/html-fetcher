---

I implemented a TypeScript service that first fetches a web page's HTML and then extracts its main content with Readability.
But for some web site when requested with my service (JS fetch API) i get a 403 Unauthorized, whilst with a browser i can view this site without any problems, partially even simply with curl.

So what are strategies that requesting these sites via a programming language also works?
Which programming languages / libraries are best for this?

A last resort will be programmatically rendering the site in a browser and getting its HTML from there. Which libraries for which programming languages offer this?

For all questions, only consider these languages: Kotlin/JVM, Python, TypeScript / npm, Go.

---

## Why You're Getting 403s

Servers detect non-browser clients through several signals:

- **Missing or wrong `User-Agent`** — the most common cause; servers blocklist known bot/fetch UAs
- **Missing browser headers** — `Accept`, `Accept-Language`, `Accept-Encoding`, `Sec-Fetch-*`, `DNT`, etc.
- **No cookie/session support** — browsers persist cookies across redirects; raw HTTP clients often don't
- **TLS fingerprinting (JA3/JA4)** — servers fingerprint the TLS handshake itself; Node.js/curl have different fingerprints than Chrome
- **HTTP/2 fingerprinting** — frame ordering, SETTINGS frames, header ordering differ per client
- **Missing Referer / Origin headers** — some sites require these to look like legitimate navigation
- **Rate limiting / IP reputation** — cloud WAFs (Cloudflare, Akamai) block datacenter IPs outright

---

## Strategy 1: Mimic a Real Browser (HTTP level)

The first thing to try — costs nothing, fixes most cases.

**Headers to always send:**
```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36
Accept: text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
Connection: keep-alive
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: none
Sec-Fetch-User: ?1
DNT: 1
```

This alone solves the majority of 403s caused by header inspection.

---

## Strategy 2: Best HTTP Libraries per Language

Beyond headers, the library you use matters for TLS/HTTP2 fingerprinting and cookie handling.

### TypeScript / Node.js

The built-in `fetch` / `undici` has a recognizable TLS fingerprint. Better options:

```ts
// got — best cookie jar, retry, redirect handling
import got from 'got';
import { CookieJar } from 'tough-cookie';

const jar = new CookieJar();
const html = await got(url, {
  cookieJar: jar,
  headers: { 'User-Agent': '...', /* full header set above */ },
  http2: true,
}).text();
```

**`got` + `tough-cookie`** is the pragmatic choice. For serious anti-bot bypass, `curl-impersonate` bindings exist but are harder to set up in Node.

---

### Python — 🏆 Best ecosystem for this problem

Python has the richest set of options here:

```python
# requests + fake-useragent: simplest starting point
import requests
from fake_useragent import UserAgent

session = requests.Session()
session.headers.update({'User-Agent': UserAgent().chrome, ...})
resp = session.get(url)
```

```python
# httpx — modern, HTTP/2 support, async-native
import httpx

async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
    resp = await client.get(url, headers={...})
```

```python
# curl_cffi — uses libcurl compiled with BoringSSL; impersonates
# Chrome's exact TLS + HTTP/2 fingerprint. Best for Cloudflare sites.
from curl_cffi.requests import AsyncSession

async with AsyncSession() as s:
    resp = await s.get(url, impersonate="chrome124")
```

**`curl_cffi`** is the strongest non-browser option available in any of these languages. It defeats TLS and HTTP/2 fingerprinting because it literally uses Chrome's TLS stack.

---

### Kotlin / JVM

```kotlin
// OkHttp — best cookie + redirect handling on JVM
val client = OkHttpClient.Builder()
    .cookieJar(JavaNetCookieJar(CookieManager()))
    .followRedirects(true)
    .build()

val request = Request.Builder()
    .url(url)
    .header("User-Agent", "Mozilla/5.0 ...")
    // ... full header set
    .build()

val html = client.newCall(request).execute().body?.string()
```

OkHttp supports HTTP/2 natively. For JVM-level TLS fingerprint spoofing there's no clean library — this is where JVM falls short vs. Python's `curl_cffi`.

---

### Go

```go
// Standard library is already quite capable
client := &http.Client{
    Jar:           cookiejar.New(nil),
    CheckRedirect: func(r *http.Request, via []*http.Request) error { return nil },
}
req, _ := http.NewRequest("GET", url, nil)
req.Header.Set("User-Agent", "Mozilla/5.0 ...")
// ... full header set
resp, _ := client.Do(req)
```

For TLS fingerprint spoofing, use **`tls-client`** (Go wrapper around `fhttp` / `cycletls`):

```go
import tls_client "github.com/bogdanfinn/tls-client"

client, _ := tls_client.NewHttpClient(
    tls_client.NewNoopLogger(),
    tls_client.WithClientProfile(profiles.Chrome_124),
)
```

---

## Strategy 3: Last Resort — Programmatic Browser (full JS rendering)

Use this when the site requires JavaScript execution, or actively defeats HTTP-level approaches.

| Language | Library | Notes |
|---|---|---|
| **TypeScript/JS** | **Playwright** | Best API, multi-browser, first-class TS support |
| **TypeScript/JS** | Puppeteer | Chrome-only, slightly lower-level than Playwright |
| **Python** | **Playwright** (`playwright`) | Same API as TS, excellent async support |
| **Python** | Selenium + undetected-chromedriver | Older API; `undetected-chromedriver` patches Chrome to evade bot detection |
| **Kotlin/JVM** | **Playwright for Java** | Official Playwright port, same capabilities |
| **Kotlin/JVM** | Selenium (WebDriver) | Mature but verbose; pair with ChromeDriver |
| **Go** | `chromedp` | CDP-based headless Chrome control; more low-level |
| **Go** | `playwright-go` | Playwright port for Go; less mature than official ports |

**Playwright** is the recommended choice in TS, Python, and JVM — consistent API, actively maintained, built-in stealth capabilities, and you can extract the final HTML after JS has rendered:

```ts
// TypeScript
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'networkidle' });
const html = await page.content(); // fully rendered DOM
await browser.close();
```

For extra stealth against bot-detection (e.g. Cloudflare's JS challenge), add the **`playwright-extra` + `puppeteer-extra-plugin-stealth`** plugin in Node.js, or **`undetected-playwright`** in Python.

---

## Decision Flow

```
Add full browser headers
        │
        ▼
   Still 403?
   ┌────┴────┐
  Yes        No ──► Done ✓
   │
   ▼
Use curl_cffi (Python) or tls-client (Go)
to spoof TLS/HTTP2 fingerprint
        │
        ▼
   Still 403?
   ┌────┴────┐
  Yes        No ──► Done ✓
   │
   ▼
Full browser rendering (Playwright)
+ stealth plugin if needed
```

For your specific case (TypeScript service), the quickest wins are: **1)** add the full header set to your existing fetch, **2)** switch to `got` + `tough-cookie`, and if that fails, **3)** call out to a small Python `curl_cffi` sidecar before reaching for Playwright.

---

For all the following, give me only a very short answer:
For a non-native English speaker, what does "impersonate" mean?
What do these headers mean:

```
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: none
Sec-Fetch-User: ?1
DNT: 1
```

As some sites also work with pure curl without manual user-agent, should we first try with curl user-agent or start with the full browser headers right away?

Which programming language is then the better fit for a web service that fetches a site's html, Pyton, TS or Kotlin?
I guess Python has the best tool support (curl_cffi), but it cannot manage such a high load than the others due to the GIL?

---

**"Impersonate"** — pretend to be someone/something else. Here: make your request look like it comes from a real browser.

---

**Headers explained:**

- `Upgrade-Insecure-Requests: 1` — "I accept HTTPS redirects" (browsers always send this)
- `Sec-Fetch-Dest: document` — the request is for a full HTML page (not an image, script, etc.)
- `Sec-Fetch-Mode: navigate` — triggered by a top-level navigation (typing URL / clicking link)
- `Sec-Fetch-Site: none` — no referring site (user typed the URL directly)
- `Sec-Fetch-User: ?1` — the navigation was triggered by a real user gesture
- `DNT: 1` — "Do Not Track" preference (servers largely ignore it, but browsers send it)

The `Sec-Fetch-*` family is particularly important — they're a consistent browser signature that raw HTTP clients typically omit.

---

**Start with full browser headers right away.** It's zero extra cost and gives you the best chance immediately. The curl UA working on some sites is coincidental — those sites simply don't check headers strictly.

---

**Python with `curl_cffi`** is the better fit, and the GIL concern is largely a non-issue here because:

- Your bottleneck is **network I/O**, not CPU — and the GIL is released during I/O
- `curl_cffi` is a C extension, so it also releases the GIL during requests
- `asyncio` + `curl_cffi`'s async session gives you high concurrency perfectly fine
- You'd only hit GIL-related limits if you were doing heavy CPU work (parsing, etc.) in parallel threads, which you'd offload or handle with multiprocessing anyway

Kotlin/JVM has better raw throughput for CPU-bound work, but for a fetch-heavy service Python is more than sufficient and the tooling advantage (`curl_cffi`) is real.

---
