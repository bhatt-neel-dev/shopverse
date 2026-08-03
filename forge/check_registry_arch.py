"""Verify every ShopVerse image in a registry really carries a linux/amd64 variant.

`docker image inspect` on a multi-arch-capable Docker Desktop reports the *host's* architecture,
so it will happily show arm64 for an image you pulled with --platform linux/amd64. Ask the
registry instead — that's the copy the target host will actually pull.

    python3 check_registry_arch.py [registry_url]     # default http://localhost:5005
"""

import json
import sys
import urllib.request

REGISTRY = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5005"

ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
])

BASE = [("mysql", "8.4"), ("postgres", "16"), ("mongo", "7"),
        ("redis", "7-alpine"), ("rabbitmq", "3.13-management-alpine")]
APPS = [(f"shopverse-{s}", "latest") for s in
        ["catalog", "order", "cart", "search", "payment", "notify",
         "storefront", "gateway", "studio-api", "studio-ui", "locust", "seed"]]


def architectures(repo: str, tag: str) -> list[str]:
    req = urllib.request.Request(f"{REGISTRY}/v2/{repo}/manifests/{tag}",
                                 headers={"Accept": ACCEPT})
    manifest = json.load(urllib.request.urlopen(req))
    if "manifests" in manifest:
        found = set()
        for entry in manifest["manifests"]:
            arch = (entry.get("platform", {}).get("architecture")
                    or entry.get("annotations", {}).get(
                        "com.docker.official-images.bashbrew.arch"))
            if arch:
                found.add(arch)
        return sorted(found)
    config = json.load(urllib.request.urlopen(
        f"{REGISTRY}/v2/{repo}/blobs/{manifest['config']['digest']}"))
    return [config.get("architecture", "?")]


def main():
    bad = []
    for repo, tag in BASE + APPS:
        name = f"{repo}:{tag}"
        try:
            arches = architectures(repo, tag)
            ok = "amd64" in arches
        except Exception as e:  # noqa: BLE001 — missing image is just a failure to report
            print(f"ERR {name:44} {e}")
            bad.append(name)
            continue
        print(f"{'OK ' if ok else 'BAD'} {name:44} {arches}")
        if not ok:
            bad.append(name)

    print(f"\n{len(BASE) + len(APPS) - len(bad)}/{len(BASE) + len(APPS)} carry amd64")
    if bad:
        print("missing amd64:", ", ".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
