"""Generate the organization gallery from public repository topics and covers"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def request(url, *, token=None, method="GET", missing_ok=False):
    headers = {"User-Agent": "psxports-profile", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers, method=method), timeout=20
            ) as response:
                return response.read() if method == "GET" else True
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def repositories(owner, token):
    result = []
    for page in range(1, 1001):
        url = "https://api.github.com/orgs/" + urllib.parse.quote(owner, safe="")
        batch = json.loads(request(url + f"/repos?type=public&per_page=100&page={page}", token=token))
        if not isinstance(batch, list):
            raise ValueError("Expected a repository list")
        result.extend(repo for repo in batch if repo["name"].endswith("-xport") and not repo["private"])
        if len(batch) < 100:
            return result
    raise ValueError("Repository pagination limit exceeded")


def cover(repo):
    # Do not send API credentials to the image host
    parts = (repo["owner"]["login"], repo["name"], repo["default_branch"])
    url = "https://raw.githubusercontent.com/" + "/".join(
        urllib.parse.quote(part, safe="") for part in parts
    ) + "/cover.png"
    if request(url, method="HEAD", missing_ok=True):
        return dict(name=repo["name"], url=repo["html_url"], topics=repo["topics"], cover=url)
    return None


def render(rows):
    groups = {"Enhanced": [], "Playable": [], "W.I.P.": []}
    for row in sorted(rows, key=lambda row: row["name"].casefold()):
        topic = "Enhanced" if "enhanced" in row["topics"] else "Playable" if "playable" in row["topics"] else "W.I.P."
        groups[topic].append(row)
    lines = ["<!-- projects:start -->", "# Projects", "",
             "<!-- A repository with several topics appears once, under enhanced before playable -->", ""]
    for title, entries in groups.items():
        lines += [f"## {title} · {len(entries)}", ""]
        if not entries:
            continue
        lines.append("<table>")
        for start in range(0, len(entries), 4):
            lines.append("  <tr>")
            for row in entries[start:start + 4]:
                name, url, image = (html.escape(row[key], quote=True) for key in ("name", "url", "cover"))
                lines.append(f'    <td align="center" valign="middle"><a href="{url}" title="{name}"><img src="{image}" alt="{name}" width="160"></a></td>')
            lines.append("  </tr>")
        lines += ["</table>", ""]
    lines.append("<!-- projects:end -->")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "psxports"))
    parser.add_argument("--output", type=Path, default=Path("profile/README.md"))
    args = parser.parse_args()
    repos = repositories(args.owner, os.environ.get("GH_TOKEN"))
    if not repos:
        raise ValueError("No public xport repositories found; keeping the existing README")
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [row for row in pool.map(cover, repos) if row is not None]
    if not rows:
        raise ValueError("No covers found; keeping the existing README")
    content = render(rows).encode("utf-8")
    if args.output.exists() and args.output.read_bytes() == content:
        print(f"Unchanged: {len(rows)} covers")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(f"Updated {args.output}: {len(rows)} covers; {len(repos) - len(rows)} repositories without covers omitted")


if __name__ == "__main__":
    main()
