# html-fetcher

Fetches a URL's HTML using a multi-tier strategy with client fallbacks.

## License

This project is licensed under the **MIT License** - see [LICENSE](LICENSE) for details.

### AGPL-3.0 Notice for Zendriver

This project includes [zendriver](https://github.com/cdpdriver/zendriver) as a dependency, which is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. 
Zendriver is an optional component that can be disabled via the environment variable `USE_ZENDRIVER=false`.

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