# html-fetcher

> Extract HTML from websites that bot protection systems try to hide.

Many modern websites use bot detection systems like Cloudflare, Akamai, DataDome, or specialized anti-bot services to block automated requests. Simple tools like `curl`, the browser's JavaScript `fetch` API, or Python's `httpx` and `requests` libraries are easily detected and blocked — they can't mimic real browser fingerprints.

html-fetcher overcomes most of these protections by using a **multi-tier fetch strategy** that escalates from fast, lightweight methods to full browser automation when needed.


## How It Works

html-fetcher implements a **cascading fetch strategy**: it starts with the fastest method and escalates to more powerful (but slower) methods only when the previous one fails.

### Available Strategies

| Strategy | Library | How It Works | Bot Detection Bypass |
|----------|---------|-------------|---------------------|
| **curl-cffi** | [curl-cffi](https://github.com/lexiforest/curl_cffi) | HTTP client that impersonates Chrome's TLS handshake, HTTP/2 fingerprint, and browser headers. | ✓ Lightweight, fast. Bypasses many Cloudflare, Akamai, and basic anti-bot checks. |
| **Camoufox** | [Camoufox](https://camoufox.com) | Stealth Firefox fork with built-in fingerprint injection (OS, CPU, canvas, fonts, etc.). | ✓ Bypasses Cloudflare Turnstile, some DataDome, and JS-based fingerprinting. |
| **Zendriver** | [Zendriver](https://github.com/cdpdriver/zendriver) | Chrome DevTools Protocol automation with undetected fingerprint. | ✓ Bypasses Cloudfront, Akamai, and advanced anti-bot systems. Optional — see `FETCH_USE_ZENDRIVER`. |

### Default Strategy Order

```
curl-cffi → Camoufox → Zendriver
```

1. **curl-cffi** is tried first — if it gets a 200, return the HTML.
2. If curl-cffi gets blocked (4xx status) or fails (network error), escalate to **Camoufox**.
3. If Camoufox also fails, escalate to **Zendriver** (if enabled).

### Customizing the Strategy Order

Override the default order using the `strategies` parameter:

```
GET /fetch?url=https://example.com&strategies=camoufox,curl-cffi
```

Or in a POST body:

```json
{
  "url": "https://example.com",
  "strategies": ["camoufox", "zendriver"]
}
```

Valid strategies: `curl-cffi`, `camoufox`, `zendriver` (case-insensitive; `curl` is a shortcut for `curl-cffi`).


## Hosted Deployment

### Quick Start (Single Command)

```bash
docker run -d --name html-fetcher -p 3330:3330 docker.dankito.net/dankito/html-fetcher:latest
```

### Docker Compose

```yaml
services:
  html-fetcher:
    image: docker.dankito.net/dankito/html-fetcher:latest
    container_name: html-fetcher
    restart: unless-stopped
    ports:
      - "3330:3330"
    environment:
      # Optional: set to false to disable Zendriver (AGPL-3.0 licensed)
      - USE_ZENDRIVER=true
    volumes:
      - html_fetcher_data:/data

volumes:
  html_fetcher_data:
```

For all supported environment variables see [Environment Variables](#environment-variables).        
For a full example see [docker-compose.yml](./docker-compose.yml) in the project root.


## REST Endpoints

### Endpoint Overview

| Method | Path            | Response | Description                                             |
|--------|-----------------|----------|---------------------------------------------------------|
| GET    | `/fetch`        | JSON     | Fetch HTML, returns JSON envelope (default)             |
| GET    | `/fetch`        | HTML     | Fetch HTML, returns raw HTML                            |
| POST   | `/fetch`        | JSON     | Fetch HTML (JSON body), returns JSON envelope (default) |
| POST   | `/fetch`        | HTML     | Fetch HTML (JSON body), returns raw HTML                |
| GET    | `/openapi.json` | JSON     | OpenAPI endpoints documentation                         |
| GET    | `/docs`         | HTML     | Swagger-UI                                              |
| GET    | `/health`       | JSON     | Health check                                            |

### Query Parameters

All `/fetch` endpoints support the following parameters, either as query parameter (GET endpoints) or in the request body (POST endpoints):

| Parameter            | Type     | Default                        | Description                                                                                 |
|----------------------|----------|--------------------------------|---------------------------------------------------------------------------------------------|
| `url`                | string   | *(required)*                   | The URL to fetch                                                                            |
| `timeout`            | float    | `None`                         | Timeout in seconds (must be > 0)                                                            |
| `user_agent`         | string   | browser UA                     | Custom User-Agent header                                                                    |
| `follow_redirects`   | bool     | `true`                         | Whether to follow HTTP redirects                                                            |
| `cookies`            | string[] | `None`                         | Cookies as `name:value` pairs, e.g. `datadome:abc123`                                       |
| `strategies`         | string[] | `curl-cffi,camoufox,zendriver` | Custom fetch strategy order, e.g. `camoufox,zendriver`                                       |
| `load_lazy_content`  | bool     | `false`                        | Scroll to bottom before capturing HTML (resolves lazy-loaded content)                       |
| `execute_javascript` | bool     | `null`                         | JavaScript execution: `null`=default, `true`=skip curl-cffi, `false`=disable JS in browsers |

Note: The response format is determined via content negotiation using the `Accept` header:
- `Accept: application/json` (default) → JSON envelope
- `Accept: text/html` → only page's HTML


### Examples

#### GET — JSON Envelope (Default)

<details>
<summary><strong>cURL</strong></summary>

```bash
curl "http://localhost:3330/fetch?url=https://example.com"
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const response = await fetch("http://localhost:3330/fetch?url=https://example.com");
const data = await response.json();
console.log(data);
// { html: "...", status_code: 200, final_url: "https://example.com", strategy: "curl-cffi" }
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.get("http://localhost:3330/fetch", params={"url": "https://example.com"})
print(response.json())
# {'html': '...', 'status_code': 200, 'final_url': 'https://example.com', 'strategy': 'curl-cffi'}
```

</details>

---

#### GET — Raw HTML

<details>
<summary><strong>cURL</strong></summary>

```bash
curl -H "Accept: text/html" "http://localhost:3330/fetch?url=https://example.com"
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const url = encodeURIComponent("https://example.com");
const response = await fetch(`http://localhost:3330/fetch?url=${url}`);
const html = await response.text();
console.log(html);
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.get("http://localhost:3330/fetch", params={"url": "https://example.com"})
print(response.text)
```

</details>

<details>
<summary><strong>cURL</strong></summary>

```bash
curl -H "Accept: text/html" "http://localhost:3330/fetch?url=https://example.com"
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const response = await fetch("http://localhost:3330/fetch?url=https://example.com", {
  headers: { "Accept": "text/html" }
});
const html = await response.text();
console.log(html);
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.get(
    "http://localhost:3330/fetch",
    params={"url": "https://example.com"},
    headers={"Accept": "text/html"}
)
print(response.text)
```

</details>

---

#### POST — Custom Strategy

<details>
<summary><strong>cURL</strong></summary>

```bash
curl -X POST "http://localhost:3330/fetch" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "strategies": ["camoufox"]}'
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const response = await fetch("http://localhost:3330/fetch", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    url: "https://example.com",
    strategies: ["camoufox"]
  })
});
const data = await response.json();
console.log(data);
// { html: "...", status_code: 200, final_url: "https://example.com", strategy: "camoufox" }
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.post("http://localhost:3330/fetch", json={
    "url": "https://example.com",
    "strategies": ["camoufox"]
})
print(response.json())
# {'html': '...', 'status_code': 200, 'final_url': 'https://example.com', 'strategy': 'camoufox'}
```

</details>

---

#### POST — With Cookies

<details>
<summary><strong>cURL</strong></summary>

```bash
curl -X POST "http://localhost:3330/fetch" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "cookies": {"datadome": "abc123DefGh"}}'
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const response = await fetch("http://localhost:3330/fetch", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    url: "https://example.com",
    cookies: { datadome: "abc123DefGh" }
  })
});
const data = await response.json();
console.log(data);
// { html: "...", status_code: 200, final_url: "https://example.com", strategy: "curl-cffi" }
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.post("http://localhost:3330/fetch", json={
    "url": "https://example.com",
    "cookies": {"datadome": "abc123DefGh"}
})
print(response.json())
# {'html': '...', 'status_code': 200, 'final_url': 'https://example.com', 'strategy': 'curl-cffi'}
```

</details>

---

#### Health Check

<details>
<summary><strong>cURL</strong></summary>

```bash
curl "http://localhost:3330/health"
```

</details>

<details>
<summary><strong>JavaScript (fetch API)</strong></summary>

```javascript
const response = await fetch("http://localhost:3330/health");
console.log(await response.json());
// { status: "ok" }
```

</details>

<details>
<summary><strong>Python (requests)</strong></summary>

```python
import requests

response = requests.get("http://localhost:3330/health")
print(response.json())
# {'status': 'ok'}
```

</details>

---

### OpenAPI Documentation

For the complete API specification (ready for import into Bruno, Postman, Insomnia, etc.):

```bash
docker run -d -p 3330:3330 --name html-fetcher docker.dankito.net/dankito/html-fetcher:latest
curl http://localhost:3330/openapi.json
```

## Environment Variables

| Variable        | Default   | Description                                                                                                   |
|-----------------|-----------|---------------------------------------------------------------------------------------------------------------|
| `HOST`          | `0.0.0.0` | Host to bind to                                                                                               |
| `PORT`          | `3330`    | Port to bind to                                                                                               |
| `ROOT_PATH`     | *(empty)* | URL path prefix (useful behind a reverse proxy)                                                               |
| `DATA_DIR`      | `/data`   | Directory for browser profiles, cache, and app data                                                           |
| `USE_ZENDRIVER` | `true`    | Enable Zendriver as fallback. Set to `0`, `false`, or `no` to disable (avoids AGPL-3.0 licensing obligations) |

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

### AGPL-3.0 Notice for Zendriver

This project includes [zendriver](https://github.com/cdpdriver/zendriver) as an optional dependency, licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. Zendriver can be disabled via `USE_ZENDRIVER=false`.

When distributing this software, you must comply with the AGPL-3.0 license obligations for zendriver, including providing its source code. 
See the [AGPL-3.0 license](https://www.gnu.org/licenses/agpl-3.0.html) for the full text.

### Dependency Licenses

| Dependency | License                              |
|------------|--------------------------------------|
| camoufox   | MIT (Python lib) / MPL-2.0 (browser) |
| curl-cffi  | MIT                                  |
| fastapi    | MIT                                  |
| pydantic   | MIT                                  |
| uvicorn    | BSD                                  |
| zendriver  | AGPL-3.0                             |