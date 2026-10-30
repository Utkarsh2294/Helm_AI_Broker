"""Download the exact locked Linux wheels using host networking, with SHA-256 checks."""

import argparse
import hashlib
import json
import os
import time
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, unquote
import certifi
import ssl
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename


def plan(tags_path, requirements_path):
    target = json.loads(Path(tags_path).read_text(encoding="utf-8-sig"))
    tags = {tag: i for i, tag in enumerate(target["tags"])}
    environment = {
        "os_name": "posix",
        "sys_platform": "linux",
        "platform_machine": "x86_64",
        "platform_system": "Linux",
        "platform_release": "",
        "platform_version": "",
        "implementation_name": "cpython",
        "implementation_version": target["python"],
        "platform_python_implementation": "CPython",
        "python_full_version": target["python"],
        "python_version": ".".join(target["python"].split(".")[:2]),
        "extra": "",
    }
    packages = {
        (canonicalize_name(p["name"]), p["version"]): p
        for p in tomllib.loads(
            (Path(__file__).resolve().parents[1] / "uv.lock").read_text(encoding="utf8")
        )["package"]
    }
    bootstrap = json.loads((Path(__file__).with_name("bootstrap-wheel.json")).read_text(encoding="utf8"))
    selected, unavailable = [bootstrap], []
    for line in Path(requirements_path).read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        version = next(iter(requirement.specifier)).version
        package = packages[canonicalize_name(requirement.name), version]
        choices = []
        for wheel in package.get("wheels", []):
            filename = unquote(urlparse(wheel["url"]).path.rsplit("/", 1)[-1])
            _, _, _, wheel_tags = parse_wheel_filename(filename)
            supported = [tags[str(tag)] for tag in wheel_tags if str(tag) in tags]
            if supported:
                choices.append((min(supported), filename, wheel))
        if not choices:
            unavailable.append(requirement.name)
        else:
            _, filename, wheel = min(choices, key=lambda item: item[0])
            selected.append({"filename": filename, **wheel})
    if unavailable:
        raise RuntimeError(f"No compatible locked wheel: {unavailable}")
    return selected


def download(wheel, directory):
    url = urlparse(wheel["url"])
    if url.scheme != "https" or url.hostname != "files.pythonhosted.org":
        raise ValueError("Unexpected wheel source")
    filename = wheel["filename"]
    if "/" in filename or "\\" in filename:
        raise ValueError("Invalid wheel filename")
    path = directory / filename
    expected = wheel["hash"].removeprefix("sha256:")
    if path.exists() and hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == expected:
        return filename + " cached"
    context = ssl.create_default_context(cafile=certifi.where())
    if wheel.get("size", 0) > 512 * 1024:
        chunk_directory = directory / ".parts" / filename
        chunk_directory.mkdir(parents=True, exist_ok=True)
        size, block = wheel["size"], 64 * 1024
        for saved in list(chunk_directory.iterdir()):
            if saved.is_file() and saved.name.isdigit() and saved.stat().st_size > block:
                data, position = saved.read_bytes(), int(saved.name)
                for offset in range(0, len(data), block):
                    (chunk_directory / str(position + offset)).write_bytes(data[offset : offset + block])

        def fetch_chunk(start):
            end = min(size - 1, start + block - 1)
            part = chunk_directory / str(start)
            if part.exists() and part.stat().st_size == end - start + 1:
                return part
            for attempt in range(3):
                try:
                    request = urllib.request.Request(wheel["url"], headers={"Range": f"bytes={start}-{end}"})
                    with urllib.request.urlopen(request, context=context, timeout=45) as response:
                        if (
                            response.status != 206
                            or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}"
                        ):
                            raise ValueError("Server did not return the requested byte range")
                        data = response.read(end - start + 1)
                    if len(data) != end - start + 1:
                        raise ValueError("Incomplete wheel range")
                    part.write_bytes(data)
                    return part
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2)

        with ThreadPoolExecutor(max_workers=4) as ranges:
            chunks = list(ranges.map(fetch_chunk, range(0, size, block)))
        digest = hashlib.sha256()
        with path.with_suffix(".part").open("wb") as output:
            for chunk in chunks:
                data = chunk.read_bytes()
                output.write(data)
                digest.update(data)
        if digest.hexdigest() != expected:
            raise ValueError("Assembled wheel hash mismatch")
        os.replace(path.with_suffix(".part"), path)
        for chunk in chunks:
            chunk.unlink()
        return filename + " verified"
    for attempt in range(3):
        try:
            digest = hashlib.sha256()
            with (
                urllib.request.urlopen(wheel["url"], context=context, timeout=90) as response,
                path.with_suffix(".part").open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("Wheel hash mismatch")
            os.replace(path.with_suffix(".part"), path)
            return filename + " verified"
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tags", default=".runtime/qa/linux-tags.json")
    parser.add_argument("--requirements", default=".runtime/qa/requirements.txt")
    parser.add_argument(
        "--directory", default=str(Path(os.environ["LOCALAPPDATA"]) / "HelmBroker/linux-wheels")
    )
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    wheels = plan(args.tags, args.requirements)
    print(
        f"Locked compatible wheels: {len(wheels)}; {sum(w.get('size', 0) for w in wheels) / 1024 / 1024:.1f} MiB",
        flush=True,
    )
    if not args.plan_only:
        directory = Path(args.directory)
        directory.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(download, wheel, directory) for wheel in wheels]
            for future in as_completed(futures):
                print(future.result(), flush=True)
