"""Build a deterministic, document-only, offline handover archive.

Run from any directory: python tools/build_handover.py [--require-clean]
Install the development requirements first. The source checkout is never changed.
"""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit
import zipfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCUMENTS = ("README.md", "AGENTS.md", "CHANGELOG.md")
STYLE = """
html{color-scheme:light;scroll-behavior:smooth}body{max-width:1000px;margin:auto;
padding:32px 24px 80px;font:16px/1.8 system-ui,'Malgun Gothic',sans-serif;
color:#172535;background:#f6f8fb}a{color:#125aba;text-underline-offset:3px}
header,article,.notice{background:white;border:1px solid #dce3ed;border-radius:12px;
padding:24px;margin:20px 0}h1,h2,h3{line-height:1.4;scroll-margin-top:20px}
h1{font-size:1.9rem}h2{margin-top:2rem}nav{display:flex;flex-wrap:wrap;gap:16px}
pre{overflow:auto;background:#edf1f7;padding:16px;border-radius:6px;line-height:1.6}
code{font-size:.9em;overflow-wrap:anywhere}table{border-collapse:collapse;display:block;
overflow:auto;width:100%;margin:16px 0}th,td{border:1px solid #d4dce7;padding:9px 12px;
text-align:left;vertical-align:top}th{background:#edf1f7}blockquote{border-left:4px solid
#9aacbf;padding-left:16px;margin-left:0}.meta{font-size:.9rem;color:#526378}
@media(max-width:600px){body{padding:12px}header,article,.notice{padding:16px}}
@media print{body{max-width:none;padding:0;background:white}header,article,.notice{
border:0;padding:0}nav{display:none}article{break-before:page}pre{white-space:pre-wrap}}
"""


def git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], encoding="utf-8"
    ).strip()


def git_state() -> dict:
    # Read only metadata: never include diffs, remote credentials, or file contents.
    raw = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1", "-z"],
        encoding="utf-8",
    ).split("\0")
    changed = []
    index = 0
    while index < len(raw) and raw[index]:
        entry = raw[index]
        record = {"status": entry[:2], "path": entry[3:]}
        index += 1
        if "R" in entry[:2] or "C" in entry[:2]:
            record["previous_path"] = raw[index]
            index += 1
        changed.append(record)
    return {
        "head": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current") or "(detached HEAD)",
        "head_committed_at": git("show", "-s", "--format=%cI", "HEAD"),
        "working_tree_dirty": bool(changed),
        "status": changed,
        "recent_commits": git("log", "-20", "--format=%H %s").splitlines(),
    }


def is_allowed_source(name: str) -> bool:
    path = PurePosixPath(name)
    return name in ROOT_DOCUMENTS or (
        len(path.parts) == 2 and path.parts[0] == "docs" and path.suffix == ".md"
    ) or (
        len(path.parts) == 3
        and path.parts[:2] == ("docs", "audit")
        and path.suffix == ".json"
    )


def read_sources() -> dict[str, bytes]:
    candidates = [ROOT / name for name in ROOT_DOCUMENTS]
    candidates.extend((ROOT / "docs").glob("*.md"))
    candidates.extend((ROOT / "docs" / "audit").glob("*.json"))
    result = {}
    for path in sorted(candidates):
        if not path.exists():
            if path.name == "CHANGELOG.md":
                continue
            raise ValueError(f"Required document is missing: {path}")
        relative = path.relative_to(ROOT)
        if any(parent.is_symlink() for parent in (path, *path.parents) if parent != ROOT):
            raise ValueError(f"Symlinks are not allowed in the bundle: {relative}")
        name = relative.as_posix()
        if not is_allowed_source(name) or not path.is_file():
            raise ValueError(f"Document outside the allowlist: {name}")
        data = path.read_bytes()
        data.decode("utf-8-sig")  # Stop on binary or incorrectly encoded documents.
        if path.suffix == ".json":
            json.loads(data)
        result[name] = data
    return result


def document_id(name: str) -> str:
    return "doc-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def html_name(name: str) -> str:
    return str(PurePosixPath(name).with_suffix(".html"))


def local_target(source: str, href: str) -> tuple[str, str] | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path:
        return source, unquote(parsed.fragment)
    if parsed.path.startswith("/"):
        raise ValueError(f"Absolute local link in {source}: {href}")
    target = posixpath.normpath(
        posixpath.join(posixpath.dirname(source), unquote(parsed.path))
    )
    return target, unquote(parsed.fragment)


class RewriteLinks(HTMLParser):
    """Rewrite generated HTML links; namespace anchors in the combined guide."""

    def __init__(self, source: str, sources: dict[str, bytes], combined: bool):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.sources = sources
        self.combined = combined
        self.parts: list[str] = []

    def rewrite_href(self, href: str) -> str:
        target = local_target(self.source, href)
        if target is None:
            return href
        name, fragment = target
        if name not in self.sources:
            raise ValueError(f"Link is outside the document bundle: {self.source}: {href}")
        if name.endswith(".md"):
            if self.combined:
                anchor = document_id(name) + ("--" + fragment if fragment else "")
                return "#" + quote(anchor)
            destination = html_name(name)
        else:
            destination = name
        base = "" if self.combined else posixpath.dirname(html_name(self.source))
        link = posixpath.relpath(destination, base or ".")
        return quote(link) + ("#" + quote(fragment) if fragment else "")

    def handle_starttag(self, tag, attrs):
        new_attrs = []
        for key, value in attrs:
            if value is not None:
                if key in {"href", "src"}:
                    value = self.rewrite_href(value)
                elif key == "id" and self.combined:
                    value = document_id(self.source) + "--" + value
            new_attrs.append(key if value is None else f'{key}="{html.escape(value, quote=True)}"')
        self.parts.append("<" + tag + (" " + " ".join(new_attrs) if new_attrs else "") + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def handle_comment(self, data):
        self.parts.append(f"<!--{data}-->")


def page(title: str, body: str, prefix: str = "") -> bytes:
    safe_title = html.escape(title)
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{safe_title} · HUFS Esports Lab</title><style>{STYLE}</style></head><body>"
        f'<header><nav><a href="{prefix}index.html">인수인계 시작</a>'
        f'<a href="{prefix}guide.html">전체 가이드</a>'
        f'<a href="{prefix}manifest.json">묶음 버전·검증 기록</a></nav></header>'
        + body + "</body></html>"
    ).encode("utf-8")


class LinksAndIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.links.append(value)
            if key == "id" and value:
                if value in self.ids:
                    raise ValueError(f"Duplicate HTML anchor: {value}")
                self.ids.add(value)


def verify_links(files: dict[str, bytes]) -> int:
    pages = {}
    for name, data in files.items():
        if name.endswith(".html"):
            parser = LinksAndIds()
            parser.feed(data.decode("utf-8"))
            pages[name] = parser
    count = 0
    for name, parser in pages.items():
        for link in parser.links:
            target = local_target(name, link)
            if target is None:
                continue
            destination, fragment = target
            if destination not in files:
                raise ValueError(f"Broken offline link: {name} -> {link}")
            if fragment and destination in pages and fragment not in pages[destination].ids:
                raise ValueError(f"Broken offline anchor: {name} -> {link}")
            count += 1
    return count


def build(require_clean: bool) -> Path:
    try:
        import markdown
    except ImportError as error:
        raise ValueError(
            "Python-Markdown is required. Run: python -m pip install -r requirements-dev.txt"
        ) from error
    state = git_state()
    if require_clean and state["working_tree_dirty"]:
        raise ValueError("Working tree has changes. Commit reviewed changes before --require-clean.")
    sources = read_sources()
    files = dict(sources)
    names = [name for name in sources if name.endswith(".md")]
    names.sort(key=lambda name: (
        0 if name == "docs/00-start-here.md" else 1 if name == "README.md" else 2,
        name,
    ))
    titles = {}
    combined = []
    for name in names:
        source = sources[name].decode("utf-8-sig")
        titles[name] = next((line[2:].strip() for line in source.splitlines()
                             if line.startswith("# ")), name)
        rendered = markdown.markdown(source, extensions=["fenced_code", "tables", "toc", "sane_lists"])
        for is_combined in (False, True):
            rewriter = RewriteLinks(name, sources, is_combined)
            rewriter.feed(rendered)
            body = "".join(rewriter.parts)
            if is_combined:
                combined.append(
                    f'<article id="{document_id(name)}"><p class="meta">원문: '
                    f'{html.escape(name)}</p>{body}</article>'
                )
            else:
                prefix = "../" * (len(PurePosixPath(name).parts) - 1)
                files[html_name(name)] = page(titles[name], "<article>" + body + "</article>", prefix)
    dirty_message = (
        "검토 중인 작업 폴더에서 생성되었습니다. 아래 커밋과 파일 내용이 다를 수 있습니다."
        if state["working_tree_dirty"] else
        "커밋 후 변경이 없는 작업 폴더에서 생성되었습니다."
    )
    notice = (
        '<div class="notice"><h1>Philips Evnia Esports Lab 인수인계</h1>'
        '<p>압축을 푼 뒤 <strong>index.html</strong>을 브라우저에서 여세요. '
        '안내 페이지는 인터넷 없이 읽을 수 있습니다. 외부 참고 자료는 인터넷 연결이 필요합니다.</p>'
        f'<p>{dirty_message} 이 묶음은 운영 배포를 증명하지 않습니다.</p>'
        f'<p class="meta">기준 커밋: {state["head"]}<br>브랜치: '
        f'{html.escape(state["branch"])}</p></div>'
    )
    navigation = "<ol>" + "".join(
        f'<li><a href="{quote(html_name(name))}">{html.escape(titles[name])}</a>'
        f' <span class="meta">(<a href="{quote(name)}">Markdown 원문</a>)</span></li>'
        for name in names
    ) + "</ol>"
    files["index.html"] = page("인수인계 시작", notice + "<article>" + navigation + "</article>")
    contents = "<ol>" + "".join(
        f'<li><a href="#{document_id(name)}">{html.escape(titles[name])}</a></li>'
        for name in names
    ) + "</ol>"
    files["guide.html"] = page("전체 가이드", notice + "<article>" + contents + "</article>" + "".join(combined))
    manifest = {
        "format_version": 1,
        "purpose": "Offline handover documentation; not source code, private data, or deployment proof.",
        "source_version": state,
        "renderer": {"package": "Markdown", "version": markdown.__version__},
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {"python": sys.version.split()[0], "zlib": zlib.ZLIB_VERSION},
        "source_allowlist": [*ROOT_DOCUMENTS, "docs/*.md", "docs/audit/*.json"],
        "source_files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in sorted(sources.items())
        },
        "generated_files": sorted(set(files) - set(sources)) + ["manifest.json"],
        "reproducibility": "Same source bytes, Git metadata, builder, Markdown and Python/zlib runtime produce identical ZIP bytes.",
    }
    files["manifest.json"] = b""  # Link verification needs the final membership, not JSON contents.
    manifest["verified_local_html_links"] = verify_links(files)
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    expected = set(sources) | {html_name(name) for name in names} | {"index.html", "guide.html", "manifest.json"}
    if set(files) != expected or any(not is_allowed_source(name) for name in sources):
        raise ValueError("Unexpected file in archive allowlist.")
    fingerprint = hashlib.sha256()
    for name, data in sorted(files.items()):
        fingerprint.update(name.encode("utf-8") + b"\0" + data + b"\0")
    output_dir = ROOT / "artifacts"
    if output_dir.is_symlink() or output_dir.resolve().parent != ROOT.resolve():
        raise ValueError("The output directory must not be a symlink.")
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f'hufs-esports-handover-{state["head"][:12]}-{fingerprint.hexdigest()[:12]}.zip'
    if output.is_symlink() or output.resolve().parent != output_dir.resolve():
        raise ValueError("The output archive must not be a symlink.")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(output) as archive:
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError("ZIP membership validation failed.")
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity validation failed.")
        for name, data in sources.items():
            if archive.read(name) != data:
                raise ValueError(f"Archived source does not match: {name}")
    print(f"Created: {output}")
    print(f"Verified: {len(files)} files; {manifest['verified_local_html_links']} offline links; ZIP integrity OK")
    print(f"Source: {state['head']}; dirty={state['working_tree_dirty']}")
    print("SHA256: " + hashlib.sha256(output.read_bytes()).hexdigest())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true", help="Refuse an uncommitted working tree.")
    arguments = parser.parse_args()
    try:
        build(arguments.require_clean)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Handover build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
