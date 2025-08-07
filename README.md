# scroll-split-tools

Automated tooling for splitting the Scroll window manager into modular components.

## Overview

This repository contains the automation system that splits [Scroll](https://github.com/scrollwm/scroll) into two independent components:

- **[scene-scroll](https://github.com/scrollwm/scene-scroll)**: Standalone scene graph library with Scroll's modifications
- **[scroll-standalone](https://github.com/scrollwm/scroll-standalone)**: Scroll window manager using external scene-scroll

## Purpose

Scroll embeds a modified version of wlroots' scene graph with custom enhancements for content and workspace scaling. This tooling extracts that scene implementation into a standalone library, enabling:

- Clean architectural separation
- Independent development and testing
- Foundation for future enhancements (e.g., SceneFX integration)
- Potential upstream contributions

## Quick Start

### Prerequisites

- Python 3.10+
- GitHub token with appropriate permissions (see [Maintaining](docs/maintaining.md))
- System dependencies (installed automatically in CI):
  - meson (>=1.3)
  - ninja-build
  - wayland-protocols (>=1.41)
  - wlroots-dev (0.20.x)

### Running a Split

The split is triggered manually via GitHub Actions:

1. Go to [Actions](../../actions) → "Split Scroll Release"
2. Click "Run workflow"
3. Enter the Scroll version (e.g., `1.11.3`)
4. Choose options:
   - **create_prs**: Create pull requests (default: true)
   - **dry_run**: Test without making changes (default: false)

The workflow will:
1. Clone the specified Scroll version
2. Extract scene files to scene-scroll
3. Update scroll-standalone to use external scene
4. Verify both compile successfully
5. Create draft PRs for review

### Local Development

```bash
# Clone the repository
git clone https://github.com/scrollwm/scroll-split-tools
cd scroll-split-tools

# Run the split locally
python split_scroll.py 1.11.3 \
  --workspace /tmp/scroll-split \
  --manifest split_manifest.json
```

## Architecture

The system uses a single unified script (`split_scroll.py`) that:

1. **Reads** from the Scroll mirror repository
2. **Extracts** scene implementation files based on the manifest
3. **Transforms** includes and build files
4. **Produces** two separate repositories
5. **Verifies** both build successfully
6. **Creates** PRs for manual review

### Key Components

- `split_scroll.py` - Main orchestration script
- `split_manifest.json` - Configuration defining which files to extract
- `.github/workflows/split-release.yml` - GitHub Actions automation
- `tests/test_split.py` - Test suite for the split logic

## Version Scheme

The split repositories use independent versioning:
- **Initial**: Scroll 1.11.3 → scene-scroll 0.0.1 + scroll-standalone 0.0.1
- **Future**: Version independently based on changes

## Configuration

The `split_manifest.json` file controls the split operation:

```json
{
  "scene_files": {
    "implementation": [
      "sway/tree/scene/scene.c",
      // ... other scene files
    ],
    "headers": [
      "sway/tree/scene/color.h",
      // ... other headers
    ]
  },
  "modifications": {
    "include_patterns": [
      // Define how includes are transformed
    ]
  }
}
```

## Maintenance

See [docs/maintaining.md](docs/maintaining.md) for detailed maintenance instructions.

## Testing

Run the test suite:

```bash
python -m pytest tests/test_split.py -v
```

## License

This tooling is MIT licensed. See [LICENSE](LICENSE) for details.
