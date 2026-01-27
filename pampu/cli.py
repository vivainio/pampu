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
        projects = list(client.projects(max_results=1000))
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


def cmd_plans(args):
    """List all plans in a project."""
    client = get_bamboo()

    try:
        plans = list(client.project_plans(args.project, max_results=1000))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not plans:
        print("No plans found.")
        return

    for plan in plans:
        key = plan.get("key", "")
        name = plan.get("shortName", "")
        print(f"{key}\t{name}")


def cmd_branches(args):
    """List branches for a plan."""
    client = get_bamboo()

    try:
        branches = list(client.plan_branches(args.plan, max_results=1000))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not branches:
        print("No branches found.")
        return

    for branch in branches:
        key = branch.get("key", "")
        name = branch.get("shortName", "")
        print(f"{key}\t{name}")


def cmd_builds(args):
    """List builds for a plan or branch."""
    client = get_bamboo()

    plan_key = args.plan
    if "-" not in plan_key:
        print("Error: Key must be in PROJECT-PLAN format (e.g., MYPROJECT-BUILD)", file=sys.stderr)
        sys.exit(1)

    try:
        # Use direct API call - works for both plans and branches
        data = client.get(f"rest/api/latest/result/{plan_key}", params={"max-results": args.limit})
        results = data.get("results", {}).get("result", [])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("No builds found.")
        return

    for r in results:
        key = r.get("key", "")
        state = r.get("state", "")
        print(f"{key}\t{state}")


def get_git_branch():
    """Get current git branch name."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_repo_config():
    """Load .pampu.toml from repo root."""
    import subprocess
    import tomllib

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = result.stdout.strip()
        config_path = f"{repo_root}/.pampu.toml"
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}


def extract_ticket(branch_name):
    """Extract ticket number like AC-12345 from branch name."""
    import re

    match = re.search(r"([A-Z]+-\d+)", branch_name, re.IGNORECASE)
    return match.group(1).upper() if match else None


def find_bamboo_branch(client, plan_key, ticket):
    """Find Bamboo branch matching ticket number."""
    branches = list(client.plan_branches(plan_key, max_results=1000))
    for branch in branches:
        name = branch.get("shortName", "")
        if ticket.lower() in name.lower():
            return branch.get("key")
    return None


def cmd_status(args):
    """Show detailed status of a build."""
    import re

    client = get_bamboo()
    build_key = args.build

    # If no build specified, try to detect from git branch
    if not build_key:
        config = get_repo_config()
        plan_key = config.get("plan")
        if not plan_key:
            print("Error: No build specified and no .pampu.toml found", file=sys.stderr)
            print("Create .pampu.toml with: plan = \"MYPROJECT-BUILD\"", file=sys.stderr)
            sys.exit(1)

        git_branch = get_git_branch()
        if not git_branch:
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)

        # Check if on main/master branch
        if git_branch in ("main", "master"):
            branch_key = plan_key
        else:
            ticket = extract_ticket(git_branch)
            if not ticket:
                print(f"Error: Could not extract ticket from branch '{git_branch}'", file=sys.stderr)
                sys.exit(1)

            branch_key = find_bamboo_branch(client, plan_key, ticket)
            if not branch_key:
                print(f"Error: No Bamboo branch found matching '{ticket}'", file=sys.stderr)
                sys.exit(1)

        # Get latest build for branch
        try:
            data = client.get(f"rest/api/latest/result/{branch_key}", params={"max-results": 1})
            results = data.get("results", {}).get("result", [])
            if not results:
                print(f"No builds found for {branch_key}")
                sys.exit(1)
            build_key = results[0].get("key")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        result = client.build_result(build_key)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not result:
        print("Build not found.")
        sys.exit(1)

    state = result.get("buildState", "Unknown")
    duration = result.get("buildDurationDescription", "")
    reason = result.get("reasonSummary", "")
    # Strip HTML tags from reason
    reason = re.sub(r"<[^>]+>", "", reason)

    print(f"Build:    {result.get('buildResultKey', build_key)}")
    print(f"State:    {state}")
    print(f"Duration: {duration}")
    print(f"Reason:   {reason}")

    passed = result.get("successfulTestCount", 0)
    failed = result.get("failedTestCount", 0)
    skipped = result.get("skippedTestCount", 0)
    if passed or failed or skipped:
        print(f"Tests:    {passed} passed, {failed} failed, {skipped} skipped")

    # Exit with error code if build failed
    if state == "Failed":
        sys.exit(1)


def relative_time(timestamp_ms):
    """Convert timestamp (ms) to relative time string."""
    import time

    if not timestamp_ms:
        return ""

    now = time.time() * 1000
    diff_seconds = (now - timestamp_ms) / 1000

    if diff_seconds < 60:
        return "just now"
    elif diff_seconds < 3600:
        mins = int(diff_seconds / 60)
        return f"{mins}m ago"
    elif diff_seconds < 86400:
        hours = int(diff_seconds / 3600)
        return f"{hours}h ago"
    elif diff_seconds < 604800:
        days = int(diff_seconds / 86400)
        return f"{days}d ago"
    else:
        weeks = int(diff_seconds / 604800)
        return f"{weeks}w ago"


def cmd_deploys(args):
    """Show deployment status for each environment."""
    client = get_bamboo()

    # Get plan/project from args or config
    plan_key = args.plan
    if not plan_key:
        config = get_repo_config()
        plan_key = config.get("project") or config.get("plan")
        if not plan_key:
            print("Error: No plan specified and no .pampu.toml found", file=sys.stderr)
            sys.exit(1)

    # Fetch entire deployment dashboard in one call
    try:
        dashboard = client.deployment_dashboard()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if plan_key is a project (no hyphen) or full plan key
    is_project = "-" not in plan_key

    # Find projects matching our plan/project
    found = False
    for item in dashboard:
        proj = item.get("deploymentProject", {})
        proj_plan = proj.get("planKey", {}).get("key", "")

        if is_project:
            if not proj_plan.startswith(plan_key + "-"):
                continue
        else:
            if proj_plan != plan_key:
                continue

        found = True
        proj_name = proj.get("name", "Unknown")
        print(f"\n{proj_name}")
        print("-" * len(proj_name))

        for env_status in item.get("environmentStatuses", []):
            env = env_status.get("environment", {})
            env_name = env.get("name", "Unknown")
            deploy = env_status.get("deploymentResult")
            if deploy:
                version_info = deploy.get("deploymentVersion", {})
                version = version_info.get("name", "?")
                state = deploy.get("deploymentState", "?")
                when = relative_time(deploy.get("finishedDate"))
                who = version_info.get("creatorDisplayName", "")
            else:
                version = "(no deployments)"
                state = ""
                when = ""
                who = ""
            print(f"  {env_name:20} {version:40} {state:10} {when:8} {who}")

    if not found:
        print(f"No deployment projects found for {plan_key}")


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

    plans_parser = subparsers.add_parser("plans", help="List plans in a project")
    plans_parser.add_argument("project", help="Project key (e.g., MYPROJECT)")

    branches_parser = subparsers.add_parser("branches", help="List branches for a plan")
    branches_parser.add_argument("plan", help="Plan key (e.g., MYPROJECT-BUILD)")

    builds_parser = subparsers.add_parser("builds", help="List builds for a plan or branch")
    builds_parser.add_argument("plan", help="Plan or branch key (e.g., MYPROJECT-BUILD or MYPROJECT-BUILD42)")
    builds_parser.add_argument("-n", "--limit", type=int, default=10, help="Number of builds (default: 10)")

    status_parser = subparsers.add_parser("status", help="Show detailed build status")
    status_parser.add_argument("build", nargs="?", help="Build key (e.g., MYPROJECT-BUILD-123). If omitted, detects from git branch")

    deploys_parser = subparsers.add_parser("deploys", help="Show deployment status for each environment")
    deploys_parser.add_argument("plan", nargs="?", help="Plan key. If omitted, reads from .pampu.toml")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "plans":
        cmd_plans(args)
    elif args.command == "branches":
        cmd_branches(args)
    elif args.command == "builds":
        cmd_builds(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "deploys":
        cmd_deploys(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
