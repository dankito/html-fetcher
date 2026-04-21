
## Headless vs. Headed vs. Virtual Display

### Headless mode
The browser runs **without any graphical output at all**. No window is created, no framebuffer is used. The rendering still happens in memory (the browser still composites layers, runs JS, etc.), but nothing is ever displayed.

**How it works internally:** Chromium has a dedicated headless mode since Chrome 112 ("new headless") that runs the full browser engine without a display server (X11/Wayland). Firefox's headless mode works similarly.

**Resource usage:** Slightly lower memory and CPU than headed because no GPU compositing is needed (though on modern Chrome the difference is smaller than it used to be). No display server needed at all.

**Detection:** Highly detectable. Leaves many signals:
- `navigator.webdriver = true`
- Missing `chrome.app`, `chrome.csi`, etc. (headless Chrome doesn't have these)
- `User-Agent` contains `HeadlessChrome`
- No GPU info, no WebGL renderer matching real hardware
- `navigator.plugins` is empty
- Screen/window properties often wrong
- Browser process list doesn't contain expected GPU helpers

### Headed mode
The browser runs with a **real GUI window** visible on a display. This is how a normal user runs a browser.

**Resource usage:** Higher than headless due to actual rendering to a display, GPU compositing, and window manager overhead. On a server with no display attached, you'd need a virtual display (see below).

**Detection:** Much harder to detect because the browser runs exactly as it would for a real user. All the missing APIs and properties are present and correct.

### Virtual display (Xvfb, X11 in Docker)
A trick where you run a **fake display server** (Xvfb = X Virtual Framebuffer) that the browser believes is a real monitor, but which outputs nothing visible. You then run the browser in **headed mode** against this virtual display.

**How it works:** `Xvfb` creates an in-memory framebuffer. The browser renders fully as if to a real screen. VNC or other tools can optionally connect to watch it.

**Resource usage:** Higher than headless — you have the overhead of Xvfb plus full headed browser rendering. Roughly 30–50% more memory and CPU vs. headless.

**Detection:** The headless score can be brought to 0% only while running in headful mode using virtual displays as a workaround — or by using Camoufox. Most detection APIs that look for headless markers return normal values because the browser actually is in headed mode. Much harder to detect than true headless.

**Summary table:**

| | Headless | Headed (real display) | Headed + Xvfb |
|---|---|---|---|
| Display server needed | No | Yes | Yes (virtual) |
| RAM | Lowest | High | Medium-high |
| CPU idle | Very low | Low-medium | Low-medium |
| Bot detectability | ❌ Worst | ✅ Best | ✅ Very good |
| Usable on a server | ✅ | ❌ | ✅ |

---

