#!/usr/bin/env python3
"""Test script to debug the update checker."""

import json
import urllib.request
import subprocess

GITHUB_API_URL = "https://api.github.com/repos/Parth-Jadhav-2004/Typely/releases/latest"

def get_installed_version():
    """Get the currently installed version from dpkg."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "typely"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception as exc:
        print(f"Could not determine installed version: {exc}")
        return "0.0.0"

def fetch_latest_release():
    """Fetch the latest release info from GitHub API."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Typely-Updater",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"Failed to fetch latest release: {exc}")
        return None

def parse_version(version):
    """Parse version string to tuple for comparison."""
    version = version.lstrip("v")
    try:
        return tuple(int(x) for x in version.split(".")[:3])
    except ValueError:
        return (0, 0, 0)

def main():
    print("=== Typely Update Checker Debug ===\n")

    # Get current version
    current = get_installed_version()
    print(f"Installed version: '{current}'")
    print(f"Parsed version: {parse_version(current)}\n")

    # Fetch latest from GitHub
    print("Fetching latest release from GitHub...")
    release = fetch_latest_release()

    if release is None:
        print("ERROR: Could not fetch release from GitHub!")
        return

    print(f"Release found!")
    print(f"  Tag name: {release.get('tag_name', 'N/A')}")
    print(f"  Name: {release.get('name', 'N/A')}")
    print(f"  Published: {release.get('published_at', 'N/A')}\n")

    latest = release.get("tag_name", "0.0.0")
    parsed_current = parse_version(current)
    parsed_latest = parse_version(latest)

    print(f"Version comparison:")
    print(f"  Current: {current} -> {parsed_current}")
    print(f"  Latest:  {latest} -> {parsed_latest}")
    print(f"  Is newer: {parsed_latest > parsed_current}\n")

    # Check for .deb assets
    print("Assets found:")
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        print(f"  - {name}")
        print(f"    URL: {url}")

if __name__ == "__main__":
    main()
