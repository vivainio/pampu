"""Pampu CLI - Main entry point."""

import argparse
import sys

from pampu import __version__
from pampu.client import get_bamboo, save_credentials, CREDENTIALS_FILE


def cmd_init(args):
    """Initialize credentials."""
    print("Pampu Setup")
    print("===========")
    print()
    print("To get a Personal Access Token:")
    print("1. Go to your Bamboo instance")
    print("2. Click your avatar (top-right) → Profile")
    print("3. Select 'Personal access tokens' tab")
    print("4. Click 'Create token'")
    print()

    url = input("Bamboo URL (e.g., https://bamboo.yourcompany.com): ").strip()
    if not url:
        print("Error: URL is required", file=sys.stderr)
        sys.exit(1)

    token = input("Personal Access Token: ").strip()
    if not token:
        print("Error: Token is required", file=sys.stderr)
        sys.exit(1)

    save_credentials(url, token)
    print(f"\nCredentials saved to {CREDENTIALS_FILE}")


def cmd_projects(args):
    """List all projects."""
    client = get_bamboo()

    try:
        projects = list(client.projects())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not projects:
        print("No projects found.")
        return

    for project in projects:
        key = project.get("key", "")
        name = project.get("name", "")
        print(f"{key}\t{name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pampu",
        description="CLI for Atlassian Bamboo",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("init", help="Initialize credentials")
    subparsers.add_parser("projects", help="List all projects")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "projects":
        cmd_projects(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
