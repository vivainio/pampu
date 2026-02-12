# pampu

CLI for Atlassian Bamboo.

## Installation

```bash
pip install pampu
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install pampu
```

## Setup

```bash
pampu init
```

This will prompt for your Bamboo URL and Personal Access Token, then save them to `~/.config/pampu/credentials.toml`.

### Getting a Personal Access Token

1. Go to your Bamboo instance
2. Click your avatar (top-right) → Profile
3. Select "Personal access tokens" tab
4. Click "Create token"

## Usage

### List projects and plans

```bash
pampu projects                    # List all projects
pampu plans MYPROJECT             # List plans in a project
pampu branches MYPROJECT-BUILD    # List branches for a plan
```

### View builds

```bash
pampu builds MYPROJECT-BUILD      # List recent builds
pampu builds MYPROJECT-BUILD -n 20  # Show more builds
pampu status MYPROJECT-BUILD-123  # Show build details
pampu logs MYPROJECT-BUILD-123    # Download and display build logs
```

### Git-aware status

When inside a git repository with Bamboo specs, `pampu status` can automatically detect the current branch:

```bash
pampu status  # Shows status for current git branch
```

### Deployments

```bash
pampu deploys                     # Show deployment status (auto-detected from bamboo.yml)
pampu deploys MYPROJECT-BUILD     # Show deployment status for a plan
pampu versions                    # List available versions
pampu version-create              # Create version from latest build on current branch
pampu version-create MYPROJECT-BUILD-123  # Create version from specific build
pampu deploy myversion DEV        # Deploy a version to an environment
pampu deploy myversion ENV1 ENV2 --chain     # Deploy sequentially, wait for each
pampu deploy myversion ENV1 ENV2 --parallel  # Deploy to all simultaneously
```

For safety reasons, `pampu deploy` refuses to deploy to any environment containing "PROD" in its name.

## Project configuration

Pampu auto-discovers project configuration from `bamboo-specs/bamboo.yml`:

```yaml
plan:
  project-key: MYPROJECT
  key: BUILD
  name: my-build
```

This is parsed to extract the plan key (`MYPROJECT-BUILD`) and project key (`MYPROJECT`).

With this config:
- `pampu status` detects your git branch and shows the matching Bamboo build
- `pampu deploys` shows deployment status without specifying a plan
- `pampu version-create` creates a version from the latest build on your current branch

Branch detection extracts ticket numbers (e.g., `PROJ-12345`) from branch names like `feature/PROJ-12345-my-feature` and matches them to Bamboo branches.

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize credentials |
| `projects` | List all projects |
| `plans <project>` | List plans in a project |
| `branches <plan>` | List branches for a plan |
| `builds <plan>` | List builds for a plan or branch |
| `status [build]` | Show detailed build status |
| `logs <build>` | Download and display build logs |
| `deploys [plan]` | Show deployment status |
| `versions [plan]` | List available versions |
| `version-create [build]` | Create a version from a build |
| `deploy <version> <env>...` | Deploy a version to one or more environments |

## License

MIT
