from src.model.fetch_result import FetchResult


class HtmlSanitizerService:

    def clean_html(self, result: FetchResult) -> str:
        html = self._inject_base_tag(result.html, result.final_url)

        return html


    def _inject_base_tag(self, html: str, base_url: str) -> str:
        """Inject <base href="base_url"> into <head> to fix relative URLs."""
        base_tag = f'<base href="{base_url}">'
        if "<head>" in html:
            return html.replace("<head>", f"<head>{base_tag}", 1)
        if "<html>" in html:
            return html.replace("<html>", f"<html><head>{base_tag}</head>", 1)
        return f"{base_tag}{html}"