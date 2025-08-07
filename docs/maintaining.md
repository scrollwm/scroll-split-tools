# Maintaining the Scroll Split Automation

This document provides guidance for maintaining the scroll-split-tools automation system.

## Overview

The automation splits the Scroll window manager into two components:
- **scene-scroll**: Extracted scene graph implementation
- **scroll-standalone**: Window manager using external scene-scroll

## Prerequisites

### GitHub Token Setup

The automation requires a GitHub Personal Access Token (PAT) with appropriate permissions:

1. Create a PAT at https://github.com/settings/tokens
2. Required permissions:
   - `repo` (full control of private repositories) - for pushing branches and creating PRs
   - `workflow` (update GitHub Action workflows) - if PRs modify workflows
   - `write:org` (read org and team membership) - for cross-repo operations in the same org
3. Add as repository secret: `SCROLL_SPLIT_TOKEN`

For fine-grained tokens, ensure these permissions:
- **Repository**: Read and write
- **Contents**: Read and write
- **Pull requests**: Read and write
- **Workflows**: Read and write

### System Dependencies

The GitHub Actions runner needs:
- Python 3.10+
- Meson build system
- Ninja
- Wayland development headers
- wlroots development package
- pkg-config

## Running the Split

### Via GitHub Actions (Recommended)

1. Go to Actions → "Split Scroll Release"
2. Click "Run workflow"
3. Enter parameters:
   - **scroll_version**: Tag/version from upstream (e.g., `1.11.3`)
   - **create_prs**: Whether to create PRs (uncheck for testing)
   - **dry_run**: Test mode without making changes

### Locally

```bash
# Clone the tools repository
git clone https://github.com/scrollwm/scroll-split-tools
cd scroll-split-tools

# Run the split
python split_scroll.py 1.11.3 \
  --workspace /tmp/scroll-split \
  --github-token $GITHUB_TOKEN
```

## Updating the Manifest

The `split_manifest.json` file controls which files are extracted and how they're modified.

### Adding New Scene Files

If Scroll adds new scene files:

```json
{
  "scene_files": {
    "implementation": [
      "sway/tree/scene/existing.c",
      "sway/tree/scene/new_file.c"  // Add here
    ]
  }
}
```

### Adding Include Patterns

If new include patterns need replacement:

```json
{
  "modifications": {
    "include_patterns": [
      {
        "from": "#include \"sway/new_pattern.h\"",
        "to": "#include <scene-scroll/new_pattern.h>"
      }
    ]
  }
}
```

## Handling Common Issues

### Build Failures

1. **Missing Dependencies**
   - Check if Scroll added new dependencies
   - Update scene-scroll's meson.build template in `split_scroll.py`

2. **Include Path Issues**
   - Verify all include patterns in manifest
   - Check for new include styles in Scroll

3. **Missing Files**
   - Update manifest with new scene files
   - Check if files were moved/renamed in Scroll

### PR Creation Failures

1. **Authentication Issues**
   - Verify GitHub token has correct permissions
   - Check token hasn't expired

2. **Branch Conflicts**
   - Delete old branches from previous runs
   - Use unique branch names with timestamps

## Testing Changes

### Unit Tests

```bash
cd tests
python -m pytest test_split.py -v
```

### Integration Testing

1. Run with `dry_run: true` first
2. Download artifacts from GitHub Actions
3. Manually verify:
   - All scene files extracted correctly
   - Include replacements applied
   - Build files generated properly

### Manual Verification

```bash
# Test scene-scroll build
cd /tmp/test-scene-scroll
meson setup build
ninja -C build

# Test scroll-standalone build
cd /tmp/test-scroll-standalone
meson setup build
ninja -C build
```

## Monitoring and Alerts

### Automated Monitoring

The workflow automatically:
- Creates issues on failure
- Uploads artifacts for debugging
- Generates detailed reports

### Manual Checks

After each split:
1. Review generated PRs
2. Check build status in both repos
3. Verify no files were missed

## Version Compatibility

### Scroll Version Requirements

- Requires Scroll versions that include the scene implementation
- Tested with Scroll 1.11.3+
- May need adjustments for major Scroll refactors

### Dependency Versions

Keep these synchronized with Scroll:
- wlroots: 0.20.x
- wayland-protocols: 1.41+
- meson: 1.3+

## Version Release Logic

The split repositories use independent versioning starting from 0.0.1:

- **Initial Release**: Scroll 1.11.3 → scene-scroll 0.0.1 + scroll-standalone 0.0.1
- **Future Releases**: Version independently based on changes
  - Patch version (0.0.x): Bug fixes, dependency updates
  - Minor version (0.x.0): New features, non-breaking changes
  - Major version (x.0.0): Breaking API changes

## Troubleshooting

### Debug Mode

Enable debug logging:
```bash
python split_scroll.py 1.11.3 --log-level DEBUG
```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Missing expected files" | Manifest outdated | Update manifest with new files |
| "Build verification failed" | Compilation error | Check dependencies and includes |
| "Failed to create PR" | GitHub auth issue | Verify token permissions |
| "Scene directory not found" | Wrong Scroll version | Verify version has scene implementation |

### Recovery Procedures

If a split fails:

1. **Partial State**
   - Check workspace for partial changes
   - Manually clean up draft PRs if created

2. **Rollback**
   - Close/delete any created PRs
   - No changes are pushed directly to main branches

3. **Retry**
   - Fix identified issues
   - Re-run with same version

## Best Practices

### Before Running a Split

1. Check upstream Scroll changes
2. Review previous split reports
3. Update manifest if needed
4. Run tests

### After Running a Split

1. Review generated report
2. Check both PRs thoroughly
3. Build both components locally
4. Test basic functionality

### Maintenance Schedule

- **Monthly**: Run for Scroll releases
- **Quarterly**: Review and update dependencies
- **Annually**: Major tooling review

## Architecture Notes

### Design Decisions

1. **Single Script**: Ensures atomic updates
2. **Manifest-Driven**: Easy updates without code changes
3. **Draft PRs**: Human review before merge
4. **Comprehensive Logging**: Full traceability

### Future Improvements

1. **Automated Testing**: Add integration with Scroll's test suite
2. **Dependency Detection**: Auto-detect new dependencies
3. **Incremental Updates**: Support for patch releases
4. **API Compatibility**: Version checking between components

## Contact

For issues or questions:
- Open issue in scroll-split-tools repository
- Tag maintainers in PR comments
- Check Scroll's documentation for upstream changes
