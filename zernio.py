#!/usr/bin/env python3
"""Zernio client for Agent Field Notes (LinkedIn only), separate from Caramelingo's Zernio account.

The API key comes from LINKEDIN_ZERNIO_API_KEY: a secret of the GitHub environment "linkedin" in the
cloud, or the .env file of this folder locally. Profile and LinkedIn account ids live in zernio.json.
Docs: https://zernio.com/llms.txt

  python3 zernio.py setup                 # create the "Agent Field Notes" profile + LinkedIn connect link
  python3 zernio.py connect-url [platform]
  python3 zernio.py accounts              # accounts in the profile; saves the LinkedIn account id
  python3 zernio.py find-post EXTERNAL_ID
"""
import argparse
import json
import mimetypes
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE / "zernio.json"
BASE = "https://zernio.com/api/v1"
KEY_NAME = "LINKEDIN_ZERNIO_API_KEY"
PROFILE_NAME = "Agent Field Notes"
TIMEZONE = "America/Sao_Paulo"


class ZernioError(RuntimeError):
    pass


def load_key():
    key = os.environ.get(KEY_NAME, "").strip()
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith(f"{KEY_NAME}="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise ZernioError(f"{KEY_NAME} is missing (GitHub environment secret, or {env} locally).")
    return key


def api(method, path, body=None, query=None, headers=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(query) if query else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {load_key()}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise ZernioError(f"Zernio {method} {path}: HTTP {e.code} {detail}") from None


def config():
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")


def ensure_profile():
    cfg = config()
    profiles = api("GET", "/profiles").get("profiles", [])
    existing = next((p for p in profiles if p.get("name") == PROFILE_NAME), None)
    if existing is None:
        existing = api("POST", "/profiles", {"name": PROFILE_NAME, "description": "LinkedIn · Agent Field Notes (personal profile)"})["profile"]
        print(f"Created profile “{PROFILE_NAME}” ({existing['_id']}).")
    cfg["profile_id"] = existing["_id"]
    save_config(cfg)
    return existing["_id"]


def connect_url(platform="linkedin"):
    query = {"profileId": config().get("profile_id") or ensure_profile()}
    if platform == "linkedin":
        query["scopes"] = "posting,analytics"  # least access: no ads or company-page scopes
    return api("GET", f"/connect/{platform}", query=query)["authUrl"]


def linkedin_accounts():
    profile_id = config().get("profile_id") or ensure_profile()
    return api("GET", "/accounts", query={"profileId": profile_id, "platform": "linkedin"}).get("accounts", [])


def account_id():
    accounts = linkedin_accounts()
    saved = config().get("linkedin_account_id")
    if saved in {a["_id"] for a in accounts}:
        return saved
    if len(accounts) == 1:
        cfg = config(); cfg["linkedin_account_id"] = accounts[0]["_id"]; save_config(cfg)
        return accounts[0]["_id"]
    raise ZernioError("No LinkedIn account (or several) in the Agent Field Notes profile; run `python3 zernio.py connect-url`.")


def profile_posts(limit=60):
    return api("GET", "/posts", query={"profileId": config()["profile_id"], "limit": limit}).get("posts", [])


def find_post(external_id):
    return api("GET", "/posts", query={"externalId": external_id}).get("posts", [])


def retry(post_id):
    return api("POST", f"/posts/{post_id}/retry", {})


def upload(path):
    path = pathlib.Path(path)
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    pre = api("POST", "/media/presign", {"filename": path.name, "contentType": ctype, "size": path.stat().st_size})
    req = urllib.request.Request(pre["uploadUrl"], data=path.read_bytes(), method="PUT")
    req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=300) as r:
        if r.status not in (200, 201, 204):
            raise ZernioError(f"Upload failed: HTTP {r.status}")
    return pre["publicUrl"]


def post_body(issue_dir, at, account):
    """Request body for one edition: the GIF (or the PDF carousel of older editions) plus the caption."""
    issue = pathlib.Path(issue_dir)
    meta = json.loads((issue / "meta.json").read_text())
    body = {"content": (issue / "caption.txt").read_text().strip(), "scheduledFor": at, "timezone": TIMEZONE,
            "externalId": f"agent-field-notes-{meta['issue']:03d}",
            "platforms": [{"platform": "linkedin", "accountId": account}]}
    if meta.get("format") == "gif":
        media = issue / "dist" / f"agent-field-notes-{meta['issue']:03d}.gif"
        item = {"type": "image", "altText": f"Animated explainer: {meta['title']}. {meta['source']['title']}."[:300]}
    else:
        media = next((issue / "dist").glob("*.pdf"))
        item = {"type": "document", "title": meta["document_title"]}
        body["platforms"][0]["platformSpecificData"] = {"documentTitle": meta["document_title"]}
    if not media.exists():
        raise ZernioError(f"{media} is missing; render the edition first.")
    return body, item, media


def check(body):
    """Ask Zernio whether LinkedIn would accept the post, so a rejection fails the run a day early."""
    result = api("POST", "/tools/validate/post", {k: body[k] for k in ("content", "platforms", "mediaItems")})
    if not result.get("valid", False):
        raise ZernioError(f"LinkedIn would reject this post: {json.dumps(result, ensure_ascii=False)[:500]}")


def create_post(issue_dir, at, dry_run=False):
    """Schedule one edition. Refuses duplicates (same externalId) and returns the post."""
    body, item, media = post_body(issue_dir, at, account_id())
    existing = find_post(body["externalId"])
    if existing:
        return {"status": "exists", "post": existing[0]}
    if dry_run:
        return {"status": "dry-run", "body": {**body, "mediaItems": [{**item, "url": f"(upload of {media.name})"}]}}
    item["url"] = upload(media)
    body["mediaItems"] = [item]
    check(body)
    created = api("POST", "/posts", body, headers={"Idempotency-Key": f"{body['externalId']}-{at}"})
    return {"status": "scheduled", "post": created.get("post", created)}


def update_post(issue_dir):
    """After a manual fix: upload the edition's media and caption again into its scheduled post."""
    body, item, media = post_body(issue_dir, None, account_id())
    existing = find_post(body["externalId"])
    if not existing:
        raise ZernioError(f"No post with externalId {body['externalId']}.")
    post = existing[0]
    if post.get("status") not in ("scheduled", "draft"):
        raise ZernioError(f"Post {post['_id']} is {post.get('status')}; only scheduled posts can change.")
    item["url"] = upload(media)
    check({**body, "mediaItems": [item]})
    updated = api("PUT", f"/posts/{post['_id']}", {"content": body["content"], "mediaItems": [item]})
    return updated.get("post", updated)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    c = sub.add_parser("connect-url"); c.add_argument("platform", nargs="?", default="linkedin")
    sub.add_parser("accounts")
    f = sub.add_parser("find-post"); f.add_argument("external_id")
    u = sub.add_parser("update-post", help="re-upload an edition's GIF and caption into its scheduled post")
    u.add_argument("issue_dir")
    a = ap.parse_args()
    try:
        if a.cmd == "setup":
            ensure_profile()
            print("LinkedIn connect link:", connect_url("linkedin"))
        elif a.cmd == "connect-url":
            print(connect_url(a.platform))
        elif a.cmd == "accounts":
            accounts = linkedin_accounts()
            for acc in accounts:
                print(acc.get("platform"), acc.get("username") or acc.get("displayName"), acc["_id"])
            print(account_id() if accounts else "No LinkedIn account connected yet.")
        elif a.cmd == "find-post":
            print(json.dumps(find_post(a.external_id), indent=2, ensure_ascii=False))
        elif a.cmd == "update-post":
            post = update_post(a.issue_dir)
            print(json.dumps({k: post.get(k) for k in ("_id", "status", "scheduledFor")}))
    except ZernioError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
