#!/usr/bin/env python3
"""Download the user's local Mighty DOOM APK copy from an Uptodown page.

The script does not commit or redistribute the APK. It resolves Uptodown's
current two-step download flow, streams the file to disk and verifies the
known SHA-256 for Mighty DOOM 1.13.1.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_PAGE = "https://mighty-doom.en.uptodown.com/android/download"
EXPECTED_SHA256 = "519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35"
EXPECTED_SIZE_HINT = 586_000_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
)


class AttrFinder(HTMLParser):
    def __init__(self, target_id: str, attribute: str) -> None:
        super().__init__()
        self.target_id = target_id
        self.attribute = attribute
        self.value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.value is not None:
            return
        values = dict(attrs)
        if values.get("id") == self.target_id:
            value = values.get(self.attribute)
            if value:
                self.value = value


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )


def read_html(url: str) -> str:
    with urllib.request.urlopen(request(url), timeout=60) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def find_attr(html: str, target_id: str, attribute: str) -> str:
    parser = AttrFinder(target_id, attribute)
    parser.feed(html)
    if not parser.value:
        raise RuntimeError(f"Não encontrei {attribute!r} em #{target_id}.")
    return parser.value


def resolve_download_url(page_url: str) -> tuple[str, str]:
    page_url = page_url.rstrip("/")
    html = read_html(page_url)

    # Previous Uptodown flow (also used by Obtainium): the app heading carries
    # a data-file-id. A second page used to expose the final data-url token
    # directly in the static HTML.
    file_id = find_attr(html, "detail-app-name", "data-file-id")
    intermediate = f"{page_url}/{urllib.parse.quote(file_id, safe='')}-x"
    intermediate_html = read_html(intermediate)

    if "download-turnstile-widget" in intermediate_html:
        raise RuntimeError(
            "Uptodown agora exige um desafio Cloudflare Turnstile antes de "
            "liberar o link de download; o token não fica mais no HTML "
            "estático, então este script não consegue resolvê-lo sozinho "
            "(e não tentamos automatizar/burlar o Turnstile). Abra "
            f"{intermediate} num navegador normal, clique em Download, "
            "copie a URL final 'https://dw.uptodown.com/dwn/...' (aba Rede "
            "do DevTools ou o gerenciador de downloads) e rode de novo com "
            "--direct-url \"<essa URL>\"."
        )

    token = find_attr(intermediate_html, "detail-download-button", "data-url")

    return file_id, f"https://dw.uptodown.com/dwn/{token}"


def download(url: str, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    h = hashlib.sha256()
    total = 0

    try:
        with urllib.request.urlopen(request(url), timeout=120) as response, tmp.open("wb") as out:
            length = response.headers.get("Content-Length")
            print(f"Download final: {response.geturl()}")
            if length:
                print(f"Tamanho informado: {int(length) / 1024 / 1024:.2f} MiB")

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                total += len(chunk)
                if total % (50 * 1024 * 1024) < 1024 * 1024:
                    print(f"  {total / 1024 / 1024:.0f} MiB baixados...", flush=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    tmp.replace(destination)
    return h.hexdigest(), total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_PAGE, help="Página /android/download da Uptodown")
    ap.add_argument("--output", default="input/mighty-doom.apk", help="Destino local do APK")
    ap.add_argument("--sha256", default=EXPECTED_SHA256, help="SHA-256 esperado; vazio desativa validação")
    ap.add_argument(
        "--direct-url",
        default=None,
        help=(
            "URL final 'https://dw.uptodown.com/dwn/...' já resolvida manualmente "
            "(necessário quando a Uptodown exige o desafio Cloudflare Turnstile "
            "antes de expor o link). Pula a raspagem da página e baixa direto daqui."
        ),
    )
    args = ap.parse_args()

    output = Path(args.output).expanduser().resolve()
    expected = args.sha256.strip().lower()

    try:
        if args.direct_url:
            download_url = args.direct_url
        else:
            file_id, download_url = resolve_download_url(args.url)
            print(f"Uptodown file id: {file_id}")
        digest, size = download(download_url, output)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
        print(f"ERRO: não foi possível obter o APK: {exc}", file=sys.stderr)
        return 2

    print(f"Arquivo: {output}")
    print(f"Tamanho: {size} bytes ({size / 1024 / 1024:.2f} MiB)")
    print(f"SHA-256: {digest}")

    if size < EXPECTED_SIZE_HINT:
        output.unlink(missing_ok=True)
        print("ERRO: arquivo é muito menor que o APK completo esperado; removido.", file=sys.stderr)
        return 3

    if expected and digest.lower() != expected:
        output.unlink(missing_ok=True)
        print("ERRO: SHA-256 diferente do esperado; arquivo removido por segurança.", file=sys.stderr)
        print(f"Esperado: {expected}", file=sys.stderr)
        print(f"Obtido:   {digest}", file=sys.stderr)
        return 4

    print("OK: APK 1.13.1 validado. O arquivo continua somente na máquina local/runner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
