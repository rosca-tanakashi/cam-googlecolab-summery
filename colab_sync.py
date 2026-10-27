#!/usr/bin/env python3
"""Google Colab ノートブックを取得・アップロードする。

対象は FILE_IDS。引数なしの download / upload は一覧の全件を処理する。
初回だけ .secrets/ に OAuth クライアント JSON が必要。

使い方:
  python colab_sync.py auth
  python colab_sync.py info
  python colab_sync.py download
  python colab_sync.py upload
  python colab_sync.py upload --yes
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

FILE_IDS = (
    "1sieu97jyNNictn2K-GVJ7HOcEESzfGWt",
    "1kybTS1FRoKnrPq4uBjdImdb0bXOwzhDu",
    "1dOeVM0cXcagAAlJm1KzSzR7A_HiaE9uE",
    "1-aDcXHEeIqRm_YyGZQKDqSPXIhP7ZGdt",
    "1-fnxr2DBhIZO7HXiIh4kGWlRqaljpVhU",
)
SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT = Path(__file__).resolve().parent
SECRETS = ROOT / ".secrets"
NOTEBOOKS = ROOT / "notebooks"
MANIFEST = NOTEBOOKS / "manifest.json"
CREDENTIAL_CANDIDATES = (
    SECRETS / "credentials.json",
    ROOT / "credentials.json",
)
TOKEN_PATH = SECRETS / "token.json"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _credentials_path() -> Path | None:
    for path in CREDENTIAL_CANDIDATES:
        if path.is_file():
            return path
    for directory in (SECRETS, ROOT):
        matches = sorted(directory.glob("client_secret*.json"))
        if matches:
            return matches[0]
    return None


def _print_setup_help() -> None:
    print(
        """OAuth クライアントの JSON が見つかりません。

次のいずれかを置いてから、もう一度実行してください。
  .secrets/credentials.json
  .secrets/client_secret....json
  credentials.json

作り方:
  1. https://console.cloud.google.com/ を開く
  2. プロジェクトを作成する
  3. 「API とサービス」→「ライブラリ」で Google Drive API を有効にする
  4. 「OAuth 同意画面」で外部を選び、自分の Gmail をテストユーザーに追加する
  5. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」
     種類は「デスクトップ アプリ」
  6. JSON をダウンロードし、上のパスに保存する
"""
    )


def _load_credentials() -> Credentials:
    client_path = _credentials_path()
    if client_path is None:
        _print_setup_help()
        raise SystemExit(1)

    creds: Credentials | None = None
    if TOKEN_PATH.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
        creds = flow.run_local_server(port=0)

    SECRETS.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _drive():
    return build("drive", "v3", credentials=_load_credentials(), cache_discovery=False)


def _api_error(exc: HttpError) -> None:
    status = getattr(exc.resp, "status", "?")
    detail = exc.reason or str(exc)
    print(f"Google Drive API エラー ({status}): {detail}", file=sys.stderr)
    if status == 404:
        print("ファイル ID が違うか、この Google アカウントから見えません。", file=sys.stderr)
    elif status == 403:
        print("Drive API が無効か、このアカウントに編集権限がありません。", file=sys.stderr)
    raise SystemExit(1)


def _safe_name(name: str) -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip().rstrip(".")
    if not cleaned:
        cleaned = "notebook"
    if not cleaned.lower().endswith(".ipynb"):
        cleaned += ".ipynb"
    return cleaned


def _file_meta(service, file_id: str) -> dict:
    try:
        return (
            service.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,modifiedTime,size,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        _api_error(exc)


def _read_manifest() -> dict:
    if not MANIFEST.is_file():
        return {"notebooks": []}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("notebooks"), list):
        return data
    if isinstance(data, dict) and data.get("fileId"):
        return {"notebooks": [data]}
    return {"notebooks": []}


def _manifest_entry(meta: dict, local_path: Path) -> dict:
    return {
        "fileId": meta["id"],
        "name": meta.get("name"),
        "mimeType": meta.get("mimeType"),
        "localPath": str(local_path.relative_to(ROOT)).replace("\\", "/"),
        "remoteModifiedTime": meta.get("modifiedTime"),
        "syncedAt": datetime.now(timezone.utc).isoformat(),
    }


def _write_manifest(meta: dict, local_path: Path) -> None:
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    data = _read_manifest()
    entry = _manifest_entry(meta, local_path)
    notebooks = [item for item in data["notebooks"] if item.get("fileId") != meta["id"]]
    notebooks.append(entry)
    order = {file_id: index for index, file_id in enumerate(FILE_IDS)}
    notebooks.sort(key=lambda item: (order.get(item.get("fileId"), len(order)), item.get("name") or ""))
    MANIFEST.write_text(
        json.dumps({"notebooks": notebooks}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _entry_for(file_id: str) -> dict | None:
    for item in _read_manifest()["notebooks"]:
        if item.get("fileId") == file_id:
            return item
    return None


def _local_path_for(meta: dict) -> Path:
    existing = _entry_for(meta["id"])
    if existing and existing.get("localPath"):
        return ROOT / existing["localPath"]

    path = NOTEBOOKS / _safe_name(meta.get("name") or "notebook")
    used = {
        item.get("localPath")
        for item in _read_manifest()["notebooks"]
        if item.get("fileId") != meta["id"] and item.get("localPath")
    }
    relative = str(path.relative_to(ROOT)).replace("\\", "/")
    if relative in used:
        path = NOTEBOOKS / f"{path.stem}_{meta['id'][:8]}.ipynb"
    return path


def _download_bytes(service, file_id: str, mime_type: str) -> bytes:
    try:
        if mime_type.startswith("application/vnd.google-apps."):
            request = service.files().export_media(
                fileId=file_id, mimeType="application/vnd.google.colaboratory"
            )
        else:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        return buffer.getvalue()
    except HttpError as exc:
        _api_error(exc)


def _print_meta(meta: dict) -> None:
    print(f"名前: {meta.get('name')}")
    print(f"ID: {meta.get('id')}")
    print(f"種類: {meta.get('mimeType')}")
    print(f"更新日時: {meta.get('modifiedTime')}")
    print(f"サイズ: {meta.get('size', '不明')}")
    if meta.get("webViewLink"):
        print(f"リンク: {meta['webViewLink']}")
    entry = _entry_for(meta["id"])
    if entry and entry.get("localPath"):
        print(f"ローカル: {entry['localPath']}")


def cmd_info(file_id: str | None) -> None:
    service = _drive()
    file_ids = [file_id] if file_id else list(FILE_IDS)
    for index, current_id in enumerate(file_ids):
        if index:
            print()
        _print_meta(_file_meta(service, current_id))


def _download_one(service, file_id: str) -> None:
    meta = _file_meta(service, file_id)
    data = _download_bytes(service, file_id, meta.get("mimeType") or "")
    try:
        notebook = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ノートブック JSON として読めませんでした: {exc}") from exc
    if not isinstance(notebook, dict) or "nbformat" not in notebook:
        raise SystemExit("取得した内容が Jupyter ノートブックではありません。")

    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    local_path = _local_path_for(meta)
    local_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_manifest(meta, local_path)
    cells = notebook.get("cells") or []
    print(f"保存しました: {local_path.relative_to(ROOT)}")
    print(f"セル数: {len(cells)}")
    print(f"リモート更新日時: {meta.get('modifiedTime')}")


def cmd_download(file_id: str | None) -> None:
    service = _drive()
    file_ids = [file_id] if file_id else list(FILE_IDS)
    failures: list[str] = []
    for index, current_id in enumerate(file_ids):
        if index:
            print()
        try:
            _download_one(service, current_id)
        except SystemExit as exc:
            failures.append(f"{current_id}: {exc}")
            print(f"失敗: {current_id}: {exc}", file=sys.stderr)
    if failures:
        raise SystemExit(1)


def _resolve_local_path(file_id: str, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = ROOT / path
        return path
    entry = _entry_for(file_id)
    if entry and entry.get("localPath"):
        return ROOT / entry["localPath"]
    raise SystemExit(
        f"{file_id} のローカルファイルがありません。先に download するか、--file を指定してください。"
    )


def _upload_one(service, file_id: str, explicit: str | None) -> None:
    local_path = _resolve_local_path(file_id, explicit)
    if not local_path.is_file():
        raise SystemExit(f"ファイルがありません: {local_path}")

    notebook = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(notebook, dict) or "nbformat" not in notebook:
        raise SystemExit("Jupyter ノートブックではありません。アップロードを中止しました。")

    meta = _file_meta(service, file_id)
    print(f"ローカル: {local_path.relative_to(ROOT)}")
    print(f"アップロード先: {meta.get('name')} ({meta.get('id')})")
    media = MediaFileUpload(
        str(local_path),
        mimetype=meta.get("mimeType") or "application/vnd.google.colaboratory",
        resumable=True,
    )
    try:
        updated = (
            service.files()
            .update(
                fileId=file_id,
                body={"name": local_path.stem},
                media_body=media,
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        _api_error(exc)

    fresh = _file_meta(service, updated["id"])
    _write_manifest(fresh, local_path)
    print(f"アップロードしました。更新日時: {fresh.get('modifiedTime')}")


def _resolve_upload_target(explicit: str) -> tuple[str, str]:
    """ローカルの .ipynb から、対応する Drive のファイル ID とパスを返す。"""
    notebooks = [
        item
        for item in _read_manifest()["notebooks"]
        if item.get("fileId") and item.get("localPath")
    ]

    def local_of(item: dict) -> Path:
        return (ROOT / item["localPath"]).resolve()

    raw = Path(explicit)
    if raw.is_absolute():
        target = raw.resolve()
    elif (ROOT / raw).is_file():
        target = (ROOT / raw).resolve()
    else:
        target = (NOTEBOOKS / raw.name).resolve()

    for item in notebooks:
        if local_of(item) == target:
            return item["fileId"], str(local_of(item))

    name_matches = [item for item in notebooks if Path(item["localPath"]).name == raw.name]
    if len(name_matches) == 1:
        item = name_matches[0]
        return item["fileId"], str(local_of(item))
    if len(name_matches) > 1:
        raise SystemExit(f"同名のノートブックが複数あります。パスを指定してください: {explicit}")

    known = "\n".join(f"  {item['localPath']}" for item in notebooks) or "  (なし)"
    raise SystemExit(f"登録済みのノートブックではありません: {explicit}\n登録済み:\n{known}")


def _upload_targets(file_id: str | None) -> list[str]:
    if file_id:
        return [file_id]
    notebooks = _read_manifest()["notebooks"]
    known = [item["fileId"] for item in notebooks if item.get("fileId") in FILE_IDS]
    if known:
        return known
    return list(FILE_IDS)


def cmd_upload(file_id: str | None, explicit: str | None, assume_yes: bool) -> None:
    file_ids = _upload_targets(file_id)
    print("次のノートブックを上書きします。")
    for current_id in file_ids:
        entry = _entry_for(current_id)
        local_path = explicit or (entry or {}).get("localPath") or "(未取得)"
        print(f"- {local_path} -> {current_id}")
    if not assume_yes:
        answer = input("この内容で上書きしますか？ [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("中止しました。")
            return

    service = _drive()
    for index, current_id in enumerate(file_ids):
        if index:
            print()
        _upload_one(service, current_id, explicit if file_id else None)


def main() -> None:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Google Colab ノートブックの取得とアップロード")
    parser.add_argument("--file-id", help="指定した 1 件だけ処理する。省略時は登録済みの全件")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="Google アカウントでログインする")
    sub.add_parser("info", help="ノートブックの情報を表示する")
    sub.add_parser("download", help="ノートブックを notebooks/ に保存する")

    upload = sub.add_parser("upload", help="ローカルのノートブックを同じ Colab ファイルへ上書きする")
    upload.add_argument("--file", help="アップロードする .ipynb。ファイル名または notebooks/ 以下のパス")
    upload.add_argument("--yes", action="store_true", help="確認なしで上書きする")

    args = parser.parse_args()
    if args.command == "auth":
        _load_credentials()
        print("ログイン済みです。token を .secrets/token.json に保存しました。")
    elif args.command == "info":
        cmd_info(args.file_id)
    elif args.command == "download":
        cmd_download(args.file_id)
    elif args.command == "upload":
        file_id = args.file_id
        explicit = args.file
        if explicit and not file_id:
            file_id, explicit = _resolve_upload_target(explicit)
        cmd_upload(file_id, explicit, args.yes)


if __name__ == "__main__":
    main()
