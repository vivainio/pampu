"""Pampu CLI - Main entry point."""

import argparse
import re
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
    """Load .pampu.toml by searching upward from current directory."""
    import tomllib
    from pathlib import Path

    current = Path.cwd()
    for directory in [current, *current.parents]:
        config_path = directory / ".pampu.toml"
        if config_path.exists():
            with open(config_path, "rb") as f:
                return tomllib.load(f)
    return {}


def extract_ticket(branch_name):
    """Extract ticket number like AC-12345 from branch name."""
    import re

    match = re.search(r"([A-Z]+-\d+)", branch_name, re.IGNORECASE)
    return match.group(1).upper() if match else None


def get_git_commit_info(sha):
    """Get commit info from local git repo. Returns (short_sha, subject) or None."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h\t%an\t%ct\t%s", sha],
            capture_output=True,
            text=True,
            check=True,
        )
        line = result.stdout.strip()
        if line:
            parts = line.split("\t", 3)
            if len(parts) == 4:
                # sha, author, timestamp (ms), subject
                return parts[0], parts[1], int(parts[2]) * 1000, parts[3]
    except subprocess.CalledProcessError:
        pass
    return None


def find_bamboo_branch(client, plan_key, ticket):
    """Find Bamboo branch matching ticket number. Returns (key, shortName)."""
    branches = list(client.plan_branches(plan_key, max_results=1000))
    for branch in branches:
        name = branch.get("shortName", "")
        if ticket.lower() in name.lower():
            return branch.get("key"), name
    return None, None


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

            branch_key, _ = find_bamboo_branch(client, plan_key, ticket)
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


def cmd_logs(args):
    """Download and display build logs."""
    client = get_bamboo()
    build_key = args.build

    # Get build info to find job keys
    try:
        data = client.get(
            f"rest/api/latest/result/{build_key}",
            params={"expand": "stages.stage.results.result"}
        )
    except Exception as e:
        print(f"Error getting build info: {e}", file=sys.stderr)
        sys.exit(1)

    # Collect all job keys from the build
    job_keys = []
    for stage in data.get("stages", {}).get("stage", []):
        for job_result in stage.get("results", {}).get("result", []):
            job_key = job_result.get("buildResultKey")
            if job_key:
                job_keys.append(job_key)

    if not job_keys:
        # Fall back to build key itself (single job build)
        job_keys = [build_key]

    # Try to download logs for each job
    for job_key in job_keys:
        if len(job_keys) > 1:
            print(f"\n=== {job_key} ===\n")

        # Try API with logEntries expansion
        try:
            log_data = client.get(
                f"rest/api/latest/result/{job_key}",
                params={"expand": "logEntries", "max-results": 99999}
            )
            log_entries = log_data.get("logEntries", {}).get("logEntry", [])
            if log_entries:
                for entry in log_entries:
                    log_text = entry.get("log", "")
                    print(log_text)
                continue
        except Exception as e:
            print(f"Error fetching logs via API: {e}", file=sys.stderr)

        # Try direct download with token auth
        try:
            log_url = f"{client.url}download/{job_key}/build_logs/{job_key}.log"
            response = client.session.get(log_url, allow_redirects=False)
            if response.status_code == 200 and "text" in response.headers.get("content-type", ""):
                print(response.text)
                continue
        except Exception:
            pass

        print(f"Could not retrieve logs for {job_key}", file=sys.stderr)


def relative_time(timestamp_ms):
    """Convert timestamp (ms) to relative time string."""
    import time

    if not timestamp_ms:
        return ""

    now = time.time() * 1000
    diff_seconds = (now - timestamp_ms) / 1000

    if diff_seconds < 60:
        return "now"
    elif diff_seconds < 3600:
        mins = int(diff_seconds / 60)
        return f"{mins}m"
    elif diff_seconds < 86400:
        hours = int(diff_seconds / 3600)
        return f"{hours}h"
    elif diff_seconds < 604800:
        days = int(diff_seconds / 86400)
        return f"{days}d"
    else:
        weeks = int(diff_seconds / 604800)
        return f"{weeks}w"


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

        # Find newest master version and count how many envs have it
        newest_master_id = 0
        newest_count = 0
        has_older = False
        for env_status in item.get("environmentStatuses", []):
            deploy = env_status.get("deploymentResult")
            if deploy:
                version_info = deploy.get("deploymentVersion", {})
                version_name = version_info.get("name", "")
                if version_name.startswith("master-"):
                    version_id = version_info.get("id", 0)
                    if version_id > newest_master_id:
                        if newest_master_id:
                            has_older = True
                        newest_master_id = version_id
                        newest_count = 1
                    elif version_id == newest_master_id:
                        newest_count += 1
                    else:
                        has_older = True
        # Show race car only if exactly one env has the newest version
        show_leader = newest_count == 1 and has_older

        for env_status in item.get("environmentStatuses", []):
            env = env_status.get("environment", {})
            env_name = env.get("name", "Unknown")
            deploy = env_status.get("deploymentResult")
            if deploy:
                version_info = deploy.get("deploymentVersion", {})
                version = version_info.get("name", "?")
                version_id = version_info.get("id")
                is_master = version.startswith("master-")
                state = deploy.get("deploymentState", "?")
                when = relative_time(deploy.get("finishedDate"))
                # Get deployer name from reasonSummary (manual) or version creator
                who = version_info.get("creatorDisplayName", "")
                if not who:
                    reason = deploy.get("reasonSummary", "")
                    if "Manual run by" in reason:
                        # Extract name from: Manual run by <a href="...">Name</a>
                        match = re.search(r'>([^<]+)</a>', reason)
                        if match:
                            who = match.group(1)
                build = version_info.get("items", [{}])[0].get("planResultKey", {}).get("key", "")
                # Add status marker
                if state == "FAILED":
                    marker = "❌"
                elif state in ("IN_PROGRESS", "QUEUED"):
                    marker = "⏳"
                elif is_master and newest_master_id and version_id != newest_master_id:
                    marker = "🐢"
                elif is_master and show_leader and version_id == newest_master_id:
                    marker = "🏎️"
                else:
                    marker = ""
            else:
                version = "(no deployments)"
                state = ""
                when = ""
                who = ""
                build = ""
                marker = ""
            if args.sha and build:
                sha = get_build_vcs_revision(client, build)
                git_info = get_git_commit_info(sha) if sha else None
                if git_info:
                    short_sha, _author, _timestamp, subject = git_info
                    # Truncate subject to fit
                    if len(subject) > 50:
                        subject = subject[:47] + "..."
                    print(f"  {env_name:20} {short_sha:10} {subject}")
                else:
                    print(f"  {env_name:20} {sha or '?':10} {version}{marker}")
            else:
                # Emoji takes 2 visual chars but varies in char count (🐢=1, 🏎️=2)
                # Use "  " placeholder when no marker to keep alignment
                marker_display = marker if marker else "  "
                version_display = version + marker_display
                pad = 40 + len(marker_display)
                print(f"  {env_name:20} {version_display:{pad}} {state:10} {when:8} {who}")

    if not found:
        print(f"No deployment projects found for {plan_key}")


def get_deployment_project_id(client, plan_key):
    """Get deployment project ID for a plan."""
    projects = list(client.get_deployment_projects_for_plan(plan_key))
    if not projects:
        return None
    return projects[0].get("id")


def get_env_shas(client, plan_key):
    """Get SHA and state for each environment. Returns dict of {env_name: (sha, state)}."""
    try:
        dashboard = client.deployment_dashboard()
    except Exception:
        return {}

    is_project = "-" not in plan_key

    env_shas = {}
    for item in dashboard:
        proj = item.get("deploymentProject", {})
        proj_plan = proj.get("planKey", {}).get("key", "")

        if is_project:
            if not proj_plan.startswith(plan_key + "-"):
                continue
        else:
            if proj_plan != plan_key:
                continue

        for env_status in item.get("environmentStatuses", []):
            env = env_status.get("environment", {})
            env_name = env.get("name", "Unknown")
            deploy = env_status.get("deploymentResult")
            if deploy:
                version_info = deploy.get("deploymentVersion", {})
                build = version_info.get("items", [{}])[0].get("planResultKey", {}).get("key", "")
                state = deploy.get("deploymentState", "")
                if build:
                    sha = get_build_vcs_revision(client, build)
                    if sha:
                        env_shas[env_name] = (sha, state)

    return env_shas


def find_oldest_sha(shas):
    """Find the oldest SHA (ancestor of all others) from a list."""
    import subprocess

    if not shas:
        return None
    if len(shas) == 1:
        return shas[0]

    # Use git merge-base to find common ancestor
    try:
        result = subprocess.run(
            ["git", "merge-base", "--octopus"] + list(shas),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        # Fallback: return first sha
        return shas[0]


def find_newest_sha(shas):
    """Find the newest SHA (descendant of all others) from a list."""
    import subprocess

    if not shas:
        return None
    if len(shas) == 1:
        return shas[0]

    # Check each SHA to see if it contains all others
    for candidate in shas:
        is_newest = True
        for other in shas:
            if other == candidate:
                continue
            # Check if candidate is descendant of other
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", other, candidate],
                capture_output=True,
            )
            if result.returncode != 0:
                is_newest = False
                break
        if is_newest:
            return candidate

    # No single newest - return the one with most recent commit date
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--date-order"] + list(shas),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:8]
    except subprocess.CalledProcessError:
        return shas[0]


def get_git_log(from_sha, to_ref="HEAD", first_parent=True):
    """Get git log as list of (sha, author, timestamp, subject) tuples."""
    import subprocess

    try:
        # Use tab separator: %h<tab>%an<tab>%ct<tab>%s (ct = committer timestamp)
        cmd = ["git", "log", "--format=%h\t%an\t%ct\t%s", "--reverse"]
        if first_parent:
            cmd.append("--first-parent")
        cmd.append(f"{from_sha}^..{to_ref}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t", 3)
                if len(parts) == 4:
                    sha, author, timestamp, subject = parts
                    commits.append((sha, author, int(timestamp) * 1000, subject))
        return commits
    except subprocess.CalledProcessError:
        return []


def cmd_timeline(args):
    """Show git history timeline with environment markers."""
    client = get_bamboo()

    # Get plan from args or config
    plan_key = args.plan
    if not plan_key:
        config = get_repo_config()
        plan_key = config.get("project") or config.get("plan")
        if not plan_key:
            print("Error: No plan specified and no .pampu.toml found", file=sys.stderr)
            sys.exit(1)

    # Get SHA and state for each environment
    env_data = get_env_shas(client, plan_key)
    if not env_data:
        print("No deployments found or could not fetch SHAs")
        sys.exit(1)

    # Extract just SHAs and track states
    env_shas = {env: sha for env, (sha, state) in env_data.items()}
    env_states = {env: state for env, (sha, state) in env_data.items()}

    # Build reverse lookup: sha -> [env_names]
    sha_to_envs = {}
    for env_name, sha in env_shas.items():
        sha_to_envs.setdefault(sha, []).append(env_name)

    # Filter SHAs to only those on main branch
    import subprocess

    def is_on_main(sha):
        """Check if SHA is an ancestor of origin/main."""
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
            capture_output=True,
        )
        return result.returncode == 0

    all_shas = set(env_shas.values())
    main_shas = [sha for sha in all_shas if is_on_main(sha)]
    branch_shas = {sha: [] for sha in all_shas if not is_on_main(sha)}

    # Track which envs are on branches
    for env_name, sha in env_shas.items():
        if sha in branch_shas:
            branch_shas[sha].append(env_name)

    if not main_shas:
        print("No deployments found on main branch")
        sys.exit(1)

    # Find oldest SHA on main
    oldest = find_oldest_sha(main_shas)
    if not oldest:
        print("Could not determine oldest deployment")
        sys.exit(1)

    # Get git log from oldest to origin/main
    commits = get_git_log(oldest, "origin/main")
    if not commits:
        print("Could not get git history")
        sys.exit(1)

    # Build stage groupings from all environments
    # Parse SERVICE_STAGE pattern (e.g., ADMIN_DEV -> service=ADMIN, stage=DEV)
    all_envs = list(env_shas.keys())
    services = set()
    stages = set()
    for env in all_envs:
        if "_" in env:
            service, stage = env.rsplit("_", 1)
            services.add(service)
            stages.add(stage)

    def format_env_label(envs):
        """Format environment list. Returns (short_label, detail_label)."""
        if not envs:
            return "", ""

        # Parse environments into service/stage, tracking states
        by_stage = {}
        ungrouped = []
        for env in envs:
            if "_" in env:
                service, stage = env.rsplit("_", 1)
                by_stage.setdefault(stage, set()).add(service)
            else:
                ungrouped.append(env)

        # Get marker for individual service/stage
        def service_marker(service, stage):
            """Return marker if service in stage has issues."""
            env = f"{service}_{stage}"
            state = env_states.get(env, "")
            if state == "FAILED":
                return "❌"
            if state in ("IN_PROGRESS", "QUEUED"):
                return "⏳"
            return ""

        # Check if all services in stage have issues
        def all_stage_marker(stage, stage_envs):
            """Return marker only if ALL services in stage have same issue."""
            markers = [service_marker(svc, stage) for svc in stage_envs]
            if markers and all(m == "❌" for m in markers):
                return "❌"
            if markers and all(m == "⏳" for m in markers):
                return "⏳"
            return ""

        # Build short labels (all X) and detail labels (partials)
        short_labels = []
        detail_labels = []
        for stage in sorted(stages):
            if stage in by_stage:
                count = len(by_stage[stage])
                total = len(services)
                if count == total:
                    marker = all_stage_marker(stage, by_stage[stage])
                    short_labels.append(f"all {stage}{marker}")
                else:
                    svc_list = ",".join(f"{svc}{service_marker(svc, stage)}" for svc in sorted(by_stage[stage]))
                    detail_labels.append(f"{stage}({svc_list})")

        # Add any ungrouped environments
        short_labels.extend(sorted(ungrouped))

        return ", ".join(short_labels), ", ".join(detail_labels)

    def abbreviate_subject(subject, max_len=60):
        """Abbreviate merge PR subjects and truncate if needed."""
        import re
        # "Merge pull request #123 from org/branch-name" -> "#123 branch-name"
        match = re.match(r"Merge pull request #(\d+) from [^/]+/(.+)", subject)
        if match:
            pr_num, branch = match.groups()
            # Strip common prefixes from branch name
            branch = re.sub(r"^(bugfix|bugfixes|feature|features|tmp)/", "", branch)
            subject = f"#{pr_num} {branch}"

        if len(subject) > max_len:
            subject = subject[:max_len - 3] + "..."
        return subject

    def short_name(author):
        """Get first name or short version of author name."""
        return author.split()[0] if author else ""

    # Print timeline
    for sha, author, timestamp, subject in commits:
        envs = sha_to_envs.get(sha, [])
        if envs:
            short_label, detail_label = format_env_label(envs)
            marker = f"<- {short_label}" if short_label else ""
        else:
            marker = ""
            detail_label = ""

        subject = abbreviate_subject(subject, 48)
        name = short_name(author)
        age = relative_time(timestamp)
        print(f"{sha}  {age:3} {name:10} {subject:50} {marker}")
        if detail_label:
            print(f"          {detail_label}")

    # Show branch deployments
    if branch_shas:
        print()
        print("On feature branches:")
        for sha, envs in branch_shas.items():
            # Get branch name containing this commit
            try:
                result = subprocess.run(
                    ["git", "branch", "-r", "--contains", sha],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branches = [b.strip().replace("origin/", "") for b in result.stdout.strip().split("\n") if b.strip() and "main" not in b]
                branch_name = branches[0] if branches else "unknown"
                # Strip common prefixes
                import re
                branch_name = re.sub(r"^(bugfix|bugfixes|feature|features|tmp)/", "", branch_name)
            except subprocess.CalledProcessError:
                branch_name = "unknown"

            git_info = get_git_commit_info(sha)
            if git_info:
                short_sha, author, timestamp, _subject = git_info
                name = short_name(author)
                age = relative_time(timestamp)
                short_label, detail_label = format_env_label(envs)
                if len(branch_name) > 40:
                    branch_name = branch_name[:37] + "..."
                marker = f"<- {short_label}" if short_label else ""
                print(f"  {short_sha}  {age:3} {name:10} {branch_name:42} {marker}")
                if detail_label:
                    print(f"            {detail_label}")


_vcs_revision_cache = {}


def get_build_vcs_revision(client, build_key):
    """Get the VCS revision (git SHA) for a build. Results are cached."""
    if build_key in _vcs_revision_cache:
        return _vcs_revision_cache[build_key]
    try:
        result = client.build_result(build_key)
        sha = result.get("vcsRevisionKey", "")[:8] if result else ""
    except Exception:
        sha = ""
    _vcs_revision_cache[build_key] = sha
    return sha


def cmd_versions(args):
    """List available versions for deployment."""
    client = get_bamboo()

    # Get plan from args or config
    plan_key = args.plan
    if not plan_key:
        config = get_repo_config()
        plan_key = config.get("plan")
        if not plan_key:
            print("Error: No plan specified and no .pampu.toml found", file=sys.stderr)
            sys.exit(1)

    proj_id = get_deployment_project_id(client, plan_key)
    if not proj_id:
        print(f"No deployment project found for {plan_key}")
        sys.exit(1)

    try:
        data = client.get(f"rest/api/latest/deploy/project/{proj_id}/versions", params={"max-result": args.limit})
        versions = data.get("versions", [])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not versions:
        print("No versions found.")
        return

    for v in versions:
        name = v.get("name", "?")
        when = relative_time(v.get("creationDate"))
        who = v.get("creatorDisplayName", "")
        build = v.get("items", [{}])[0].get("planResultKey", {}).get("key", "")
        if args.sha and build:
            sha = get_build_vcs_revision(client, build)
            git_info = get_git_commit_info(sha) if sha else None
            if git_info:
                short_sha, _author, _timestamp, subject = git_info
                if len(subject) > 60:
                    subject = subject[:57] + "..."
                print(f"{name:30} {short_sha:10} {subject}")
            else:
                print(f"{name:30} {sha or '?':10} (not in local repo)")
        else:
            print(f"{name:50} {when:8} {who:20} {build}")


def cmd_version_create(args):
    """Create a version from a build."""
    client = get_bamboo()

    config = get_repo_config()
    plan_key = config.get("plan")
    if not plan_key:
        print("Error: No .pampu.toml found with plan", file=sys.stderr)
        sys.exit(1)

    build_key = args.build

    # If no build specified, get latest from current branch
    branch_name = None
    if not build_key:
        git_branch = get_git_branch()
        if not git_branch:
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)

        if git_branch in ("main", "master"):
            branch_key = plan_key
            branch_name = "master"
        else:
            ticket = extract_ticket(git_branch)
            if not ticket:
                print(f"Error: Could not extract ticket from branch '{git_branch}'", file=sys.stderr)
                sys.exit(1)

            branch_key, branch_name = find_bamboo_branch(client, plan_key, ticket)
            if not branch_key:
                print(f"Error: No Bamboo branch found matching '{ticket}'", file=sys.stderr)
                sys.exit(1)

        # Get latest build
        data = client.get(f"rest/api/latest/result/{branch_key}", params={"max-results": 1})
        results = data.get("results", {}).get("result", [])
        if not results:
            print(f"No builds found for {branch_key}")
            sys.exit(1)
        build_key = results[0].get("key")
        build_number = results[0].get("buildNumber")
    else:
        # Extract build number from provided build key
        build_number = build_key.split("-")[-1]
        branch_name = None

    proj_id = get_deployment_project_id(client, plan_key)
    if not proj_id:
        print(f"No deployment project found for {plan_key}")
        sys.exit(1)

    # Create version with branch-number format
    if branch_name:
        version_name = f"{branch_name}-{build_number}"
    else:
        version_name = build_key.replace(plan_key + "-", "")

    try:
        resp = client.session.post(
            f"{client.url}rest/api/latest/deploy/project/{proj_id}/version",
            json={"planResultKey": build_key, "name": version_name},
        )
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} - {resp.text}", file=sys.stderr)
            sys.exit(1)
        result = resp.json()
        print(f"Created version: {result.get('name')}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def wait_for_deployment(client, result_id, env_name, poll_interval=5):
    """Wait for deployment to complete. Returns True if successful."""
    import time

    while True:
        try:
            result = client.get(f"rest/api/latest/deploy/result/{result_id}")
            state = result.get("deploymentState", "")
            life_cycle = result.get("lifeCycleState", "")

            if life_cycle == "FINISHED":
                if state == "SUCCESS":
                    print(f"  {env_name}: SUCCESS")
                    return True
                else:
                    print(f"  {env_name}: FAILED ({state})")
                    return False

            time.sleep(poll_interval)
        except Exception as e:
            print(f"  {env_name}: Error polling status: {e}", file=sys.stderr)
            return False


def cmd_deploy(args):
    """Deploy a version to one or more environments."""
    client = get_bamboo()

    plan_key = args.plan
    if not plan_key:
        config = get_repo_config()
        plan_key = config.get("plan")
    if not plan_key:
        print("Error: No plan specified and no .pampu.toml found", file=sys.stderr)
        sys.exit(1)

    proj_id = get_deployment_project_id(client, plan_key)
    if not proj_id:
        print(f"No deployment project found for {plan_key}")
        sys.exit(1)

    # Find version ID by name
    version_name = args.version
    try:
        data = client.get(f"rest/api/latest/deploy/project/{proj_id}/versions", params={"max-result": 100})
        versions = data.get("versions", [])
        version_id = None
        for v in versions:
            if v.get("name") == version_name:
                version_id = v.get("id")
                break
        if not version_id:
            print(f"Error: Version '{version_name}' not found", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Get project environments
    try:
        proj_details = client.deployment_project(proj_id)
        environments = proj_details.get("environments", [])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve environment names to IDs
    env_targets = []
    for env_name in args.environments:
        if "PROD" in env_name.upper():
            print(f"Error: Deploying to PROD environments is not allowed ({env_name})", file=sys.stderr)
            sys.exit(1)
        env_id = None
        for env in environments:
            if env.get("name") == env_name:
                env_id = env.get("id")
                break
        if not env_id:
            print(f"Error: Environment '{env_name}' not found", file=sys.stderr)
            print("Available environments:")
            for env in environments:
                print(f"  {env.get('name')}")
            sys.exit(1)
        env_targets.append((env_name, env_id))

    # Deploy based on mode
    if args.chain:
        print(f"Deploying {version_name} to {len(env_targets)} environments (chained):")
        for env_name, env_id in env_targets:
            print(f"  {env_name}: deploying...")
            try:
                result = client.trigger_deployment_for_version_on_environment(version_id, env_id)
                result_id = result.get("deploymentResultId")
                if not wait_for_deployment(client, result_id, env_name):
                    print("Chain stopped due to failure.", file=sys.stderr)
                    sys.exit(1)
            except Exception as e:
                print(f"  {env_name}: Error: {e}", file=sys.stderr)
                sys.exit(1)
        print("All deployments completed successfully.")

    elif args.parallel:
        print(f"Deploying {version_name} to {len(env_targets)} environments (parallel):")
        for env_name, env_id in env_targets:
            try:
                result = client.trigger_deployment_for_version_on_environment(version_id, env_id)
                print(f"  {env_name}: triggered (ID: {result.get('deploymentResultId')})")
            except Exception as e:
                print(f"  {env_name}: Error: {e}", file=sys.stderr)

    else:
        # Single environment, original behavior
        env_name, env_id = env_targets[0]
        try:
            result = client.trigger_deployment_for_version_on_environment(version_id, env_id)
            print(f"Deployment triggered: {result.get('deploymentResultId', 'OK')}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


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

    logs_parser = subparsers.add_parser("logs", help="Download and display build logs")
    logs_parser.add_argument("build", help="Build key (e.g., MYPROJECT-BUILD-123)")

    deploys_parser = subparsers.add_parser("deploys", help="Show deployment status for each environment")
    deploys_parser.add_argument("plan", nargs="?", help="Plan key. If omitted, reads from .pampu.toml")
    deploys_parser.add_argument("--sha", action="store_true", help="Show git SHA for each deployment")

    versions_parser = subparsers.add_parser("versions", help="List available versions")
    versions_parser.add_argument("plan", nargs="?", help="Plan key. If omitted, reads from .pampu.toml")
    versions_parser.add_argument("-n", "--limit", type=int, default=20, help="Number of versions (default: 20)")
    versions_parser.add_argument("--sha", action="store_true", help="Show git SHA for each version")

    version_create_parser = subparsers.add_parser("version-create", help="Create a version from a build")
    version_create_parser.add_argument("build", nargs="?", help="Build key. If omitted, uses latest from current branch")

    deploy_parser = subparsers.add_parser("deploy", help="Deploy a version to one or more environments")
    deploy_parser.add_argument("version", help="Version name")
    deploy_parser.add_argument("environments", nargs="+", help="Environment name(s)")
    deploy_parser.add_argument("--plan", help="Plan key (default: from .pampu.toml)")
    deploy_parser.add_argument("--chain", action="store_true", help="Deploy sequentially, waiting for each to complete")
    deploy_parser.add_argument("--parallel", action="store_true", help="Deploy to all environments simultaneously")

    timeline_parser = subparsers.add_parser("timeline", help="Show git history with environment markers")
    timeline_parser.add_argument("plan", nargs="?", help="Plan key. If omitted, reads from .pampu.toml")

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
    elif args.command == "logs":
        cmd_logs(args)
    elif args.command == "deploys":
        cmd_deploys(args)
    elif args.command == "versions":
        cmd_versions(args)
    elif args.command == "version-create":
        cmd_version_create(args)
    elif args.command == "deploy":
        cmd_deploy(args)
    elif args.command == "timeline":
        cmd_timeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
