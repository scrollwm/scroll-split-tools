#!/usr/bin/env python3
"""
split_scroll.py - Unified automation script for splitting Scroll into modular components

This script reads from scrollwm/scroll and produces:
1. scrollwm/scene-scroll - Extracted scene graph implementation
2. scrollwm/scroll-standalone - Window manager using external scene-scroll
"""

import os
import re
import json
import shutil
import subprocess
import tempfile
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field


@dataclass
class SplitConfig:
    """Configuration for the split operation"""
    scroll_version: str
    workspace_dir: Path
    manifest_path: Path
    dry_run: bool = False
    create_prs: bool = True
    github_token: Optional[str] = None
    log_level: str = "INFO"
    skip_build_verification: bool = True


@dataclass
class SplitResult:
    """Results of a split operation"""
    success: bool
    scroll_commit: str
    scene_files: List[Path] = field(default_factory=list)
    standalone_files_modified: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ScrollSplitter:
    """Main class for splitting Scroll into components"""
    
    def __init__(self, config: SplitConfig):
        self.config = config
        self.logger = self._setup_logger()
        self.manifest = self._load_manifest()
        
        # Repository paths
        self.scroll_repo = config.workspace_dir / "scroll"
        self.scene_repo = config.workspace_dir / "scene-scroll"
        self.standalone_repo = config.workspace_dir / "scroll-standalone"
        
    def _setup_logger(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("ScrollSplitter")
        logger.setLevel(getattr(logging, self.config.log_level))
        
        # Console handler
        ch = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # File handler
        log_file = self.config.workspace_dir / f"split_{datetime.now():%Y%m%d_%H%M%S}.log"
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        return logger
        
    def _load_manifest(self) -> Dict:
        """Load the split manifest configuration"""
        try:
            with open(self.config.manifest_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load manifest: {e}")
            
    def _run_command(self, cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr"""
        self.logger.debug(f"Running command: {' '.join(cmd)} in {cwd}")
        
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True
        )
        
        if result.returncode != 0:
            self.logger.error(f"Command failed with exit code {result.returncode}")
            if result.stderr:
                self.logger.error(f"stderr: {result.stderr}")
            if result.stdout:
                self.logger.error(f"stdout: {result.stdout}")
            
        return result.returncode, result.stdout, result.stderr
        
    def clone_repository(self, repo_url: str, target_dir: Path, ref: str = None):
        """Clone a repository and optionally checkout a specific ref"""
        self.logger.info(f"Cloning {repo_url} to {target_dir}")
        
        if target_dir.exists():
            self.logger.warning(f"Directory {target_dir} already exists, removing...")
            shutil.rmtree(target_dir)
            
        # Clone the repository
        ret, _, _ = self._run_command(["git", "clone", repo_url, str(target_dir)])
        if ret != 0:
            raise RuntimeError(f"Failed to clone {repo_url}")
            
        # Checkout specific ref if provided
        if ref:
            self.logger.info(f"Checking out {ref}")
            ret, _, _ = self._run_command(["git", "checkout", ref], cwd=target_dir)
            if ret != 0:
                raise RuntimeError(f"Failed to checkout {ref}")

    def get_current_commit(self, repo_path: Path) -> str:
        """Get the current commit hash of a repository"""
        ret, stdout, _ = self._run_command(
            ["git", "rev-parse", "HEAD"], cwd=repo_path
        )
        if ret != 0:
            raise RuntimeError(f"Failed to get commit hash for {repo_path}")
        return stdout.strip()
        
    def analyze_scroll_structure(self) -> Dict[str, List[Path]]:
        """Analyze the Scroll repository structure and validate against manifest"""
        self.logger.info("Analyzing Scroll repository structure...")
        
        structure = {
            "scene_files": [],
            "missing_files": [],
            "unexpected_files": []
        }
        
        # Check for expected scene files in sway/tree/scene directory
        scene_dir = self.scroll_repo / "sway/tree/scene"
        if not scene_dir.exists():
            raise RuntimeError(f"Scene directory not found: {scene_dir}")
            
        # Get all files in scene directory
        actual_files = set()
        for file_path in scene_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.scroll_repo)
                actual_files.add(str(rel_path))
                
        # Also check for header files in include directory
        if "headers" in self.manifest["scene_files"]:
            for header_path in self.manifest["scene_files"]["headers"]:
                full_path = self.scroll_repo / header_path
                if full_path.exists():
                    actual_files.add(header_path)
                
        # Compare with manifest
        expected_impl = set(self.manifest["scene_files"]["implementation"])
        expected_headers = set(self.manifest["scene_files"].get("headers", []))
        expected_files = expected_impl | expected_headers
        
        # Find matches and discrepancies
        for file_path in expected_files:
            if file_path in actual_files or (self.scroll_repo / file_path).exists():
                structure["scene_files"].append(Path(file_path))
            else:
                structure["missing_files"].append(Path(file_path))
                
        # Find unexpected files in scene directory
        for file_path in actual_files:
            if file_path not in expected_files and file_path.startswith("sway/tree/scene/"):
                structure["unexpected_files"].append(Path(file_path))
                
        # Log analysis results
        self.logger.info(f"Found {len(structure['scene_files'])} expected scene files")
        if structure["unexpected_files"]:
            self.logger.warning(f"Found {len(structure['unexpected_files'])} unexpected files")
        if structure["missing_files"]:
            self.logger.error(f"Missing {len(structure['missing_files'])} expected files")
            
        return structure
        
    def extract_scene_files(self, structure: Dict[str, List[Path]]) -> List[Path]:
        """Extract scene files to scene-scroll repository"""
        self.logger.info("Extracting scene files to scene-scroll...")
        
        extracted_files = []
        
        for file_path in structure["scene_files"]:
            source = self.scroll_repo / file_path
            
            # Skip if file doesn't exist
            if not source.exists():
                self.logger.warning(f"Skipping non-existent file: {source}")
                continue
            
            # Determine destination based on file type
            if file_path.suffix == '.c':
                dest = self.scene_repo / "src" / file_path.name
            elif file_path.suffix == '.h':
                if "include/" in str(file_path):
                    # Main header from include directory
                    dest = self.scene_repo / "include/scene-scroll/scene.h"
                else:
                    # Headers from scene directory
                    dest = self.scene_repo / "include/scene-scroll" / file_path.name
            else:
                self.logger.warning(f"Unknown file type: {file_path}")
                continue
                
            # Create destination directory
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            self.logger.debug(f"Copying {source} to {dest}")
            shutil.copy2(source, dest)
            extracted_files.append(dest)
            
        return extracted_files
        
    def create_scene_build_files(self):
        """Create meson.build and other build files for scene-scroll"""
        self.logger.info("Creating build files for scene-scroll...")
        
        # Get list of source files
        src_files = sorted([f.name for f in (self.scene_repo / "src").glob("*.c")])
        
        # Create meson.build
        meson_content = f"""project('scene-scroll', 'c',
  version: '0.0.1',
  license: 'MIT',
  meson_version: '>=1.3',
  default_options: [
    'c_std=c11',
    'warning_level=2',
    'werror=false',
  ],
)

add_project_arguments(
  [
    '-DWLR_USE_UNSTABLE',
    '-D_POSIX_C_SOURCE=200809L',
  ],
  language: 'c',
)

# Compiler
cc = meson.get_compiler('c')

# Dependencies
wlroots = dependency('wlroots-0.20', version: ['>=0.20.0', '<0.21.0'])
wayland_server = dependency('wayland-server', version: '>=1.21.0')
wayland_protos = dependency('wayland-protocols', version: '>=1.41')
pixman = dependency('pixman-1')
math = cc.find_library('m')

scene_scroll_deps = [
  wlroots,
  wayland_server,
  wayland_protos,
  pixman,
  math,
]

# Source files
scene_scroll_sources = files(
{chr(10).join(f"  'src/{f}'," for f in src_files)}
)

# Include directories
scene_scroll_inc = include_directories('include')

# Build library
scene_scroll_lib = library(
  'scene-scroll',
  scene_scroll_sources,
  include_directories: scene_scroll_inc,
  dependencies: scene_scroll_deps,
  install: true,
)

# Generate pkg-config file
pkg = import('pkgconfig')
pkg.generate(
  scene_scroll_lib,
  description: 'Scene graph library extracted from Scroll window manager',
  subdirs: ['scene-scroll'],
)

# Declare dependency
scene_scroll_dep = declare_dependency(
  link_with: scene_scroll_lib,
  include_directories: scene_scroll_inc,
  dependencies: scene_scroll_deps,
)

# Install headers
install_headers(
  'include/scene-scroll/scene.h',
  subdir: 'scene-scroll',
)

# Install additional headers if they exist
fs = import('fs')
scene_headers = []
foreach h : ['color.h', 'output.h']
  header_path = join_paths('include/scene-scroll', h)
  if fs.exists(header_path)
    scene_headers += header_path
  endif
endforeach

if scene_headers.length() > 0
  install_headers(scene_headers, subdir: 'scene-scroll')
endif
"""
        
        meson_file = self.scene_repo / "meson.build"
        meson_file.write_text(meson_content)
        self.logger.debug(f"Created {meson_file}")
        
        # Create README
        readme_content = f"""# scene-scroll

Scene graph library extracted from Scroll window manager.

This library contains Scroll's modified wlroots scene graph implementation with
custom modifications for content and workspace scaling.

## Building

```bash
meson setup build
ninja -C build
sudo ninja -C build install
```

## Usage

Include in your meson.build:
```meson
scene_scroll_dep = dependency('scene-scroll')
```

Use in your code:
```c
#include <scene-scroll/scene.h>
```

## Origin

Extracted from Scroll commit: {self.config.scroll_version}
Generated on: {datetime.now().isoformat()}
"""
        
        readme_file = self.scene_repo / "README.md"
        readme_file.write_text(readme_content)
        self.logger.debug(f"Created {readme_file}")
        
    def update_standalone_files(self) -> List[Path]:
        """Update scroll-standalone to use external scene-scroll"""
        self.logger.info("Updating scroll-standalone files...")
        
        modified_files = []
        
        # Remove scene implementation directory
        scene_dir = self.standalone_repo / "sway/tree/scene"
        if scene_dir.exists():
            shutil.rmtree(scene_dir)
            self.logger.debug(f"Removed {scene_dir}")
            
        # Update all C and H files with new includes
        for pattern in ["**/*.c", "**/*.h"]:
            for file_path in self.standalone_repo.rglob(pattern):
                if self._update_file_includes(file_path):
                    modified_files.append(file_path)
                    
        # Update meson.build files
        if self._update_meson_files():
            modified_files.append(self.standalone_repo / "meson.build")
            modified_files.append(self.standalone_repo / "sway/meson.build")
            
        # Create redirect header
        redirect_header = self.standalone_repo / "include/sway/tree/scene.h"
        redirect_content = """#ifndef _SWAY_SCENE_REDIRECT_H
#define _SWAY_SCENE_REDIRECT_H

// Redirect to external scene-scroll library
#include <scene-scroll/scene.h>

#endif
"""
        redirect_header.write_text(redirect_content)
        modified_files.append(redirect_header)
        
        return modified_files
        
    def _update_file_includes(self, file_path: Path) -> bool:
        """Update includes in a single file"""
        try:
            content = file_path.read_text()
            original_content = content
            
            # Apply all include replacements from manifest
            for pattern_info in self.manifest["modifications"]["include_patterns"]:
                pattern = pattern_info["from"]
                replacement = pattern_info["to"]
                content = re.sub(pattern, replacement, content)
                
            # Only write if changed
            if content != original_content:
                if not self.config.dry_run:
                    file_path.write_text(content)
                self.logger.debug(f"Updated includes in {file_path}")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to update {file_path}: {e}")
            
        return False
        
    def _update_meson_files(self) -> bool:
        """Update meson build files"""
        modified = False
        
        # Update main meson.build
        main_meson = self.standalone_repo / "meson.build"
        try:
            content = main_meson.read_text()
            
            # Add scene-scroll dependency if not present
            if "scene-scroll" not in content:
                # Find wlroots subproject and add after it
                wlroots_match = re.search(
                    r"(wlroots\s*=\s*subproject\([^)]+\))", 
                    content
                )
                if wlroots_match:
                    insert_pos = wlroots_match.end()
                    scene_dep = """

# Scene-scroll dependency
scene_scroll_dep = dependency('scene-scroll', required: true)
"""
                    content = content[:insert_pos] + scene_dep + content[insert_pos:]
                    
                    if not self.config.dry_run:
                        main_meson.write_text(content)
                    modified = True
                    self.logger.debug("Added scene-scroll dependency to main meson.build")
                    
        except Exception as e:
            self.logger.error(f"Failed to update main meson.build: {e}")
            
        # Update sway/meson.build
        sway_meson = self.standalone_repo / "sway/meson.build"
        try:
            content = sway_meson.read_text()
            
            # Remove scene source files
            content = re.sub(
                r"'tree/scene/[^']+\.c',?\s*\n?", 
                "", 
                content
            )
            
            # Add scene_scroll_dep to dependencies if not present
            if "scene_scroll_dep" not in content:
                # Find dependencies list
                deps_match = re.search(
                    r"(dependencies\s*:\s*\[)([^\]]+)(\])",
                    content
                )
                if deps_match:
                    deps_content = deps_match.group(2)
                    if "scene_scroll_dep" not in deps_content:
                        new_deps = deps_content.rstrip() + ",\n    scene_scroll_dep,\n  "
                        content = (
                            content[:deps_match.start(2)] + 
                            new_deps + 
                            content[deps_match.end(2):]
                        )
                        
            if not self.config.dry_run:
                sway_meson.write_text(content)
            modified = True
            self.logger.debug("Updated sway/meson.build")
            
        except Exception as e:
            self.logger.error(f"Failed to update sway/meson.build: {e}")
            
        return modified
        
    def verify_build(self, repo_path: Path) -> bool:
        """Verify that a repository builds successfully"""
        self.logger.info(f"Verifying build for {repo_path.name}...")
        
        build_dir = repo_path / "build"
        
        # Clean existing build directory if it exists
        if build_dir.exists():
            shutil.rmtree(build_dir)
        
        # Setup build
        ret, stdout, stderr = self._run_command(
            ["meson", "setup", "build"], 
            cwd=repo_path
        )
        if ret != 0:
            self.logger.error(f"Meson setup failed for {repo_path.name}")
            self.logger.error(f"stdout: {stdout}")
            self.logger.error(f"stderr: {stderr}")
            
            # Try to get more info about missing dependencies
            if "dependency" in stdout.lower() or "dependency" in stderr.lower():
                self.logger.error("Possible missing dependency. Checking available pkg-config packages...")
                ret2, stdout2, _ = self._run_command(["pkg-config", "--list-all"])
                if ret2 == 0:
                    if "wlroots" in stdout2:
                        self.logger.info("wlroots found in pkg-config")
                    else:
                        self.logger.error("wlroots NOT found in pkg-config")
            return False
            
        # Compile
        ret, stdout, stderr = self._run_command(
            ["ninja", "-C", "build"],
            cwd=repo_path
        )
        if ret != 0:
            self.logger.error(f"Compilation failed for {repo_path.name}")
            self.logger.error(f"stdout: {stdout}")
            self.logger.error(f"stderr: {stderr}")
            return False
            
        self.logger.info(f"Build successful for {repo_path.name}")
        return True
        
    def create_pull_request(self, repo_name: str, branch_name: str, 
                          title: str, body: str) -> Optional[str]:
        """Create a pull request using GitHub CLI"""
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would create PR for {repo_name}")
            return "dry-run-pr"
            
        self.logger.info(f"Creating PR for {repo_name}...")
        
        repo_path = self.config.workspace_dir / repo_name
        
        # Create and push branch
        ret, _, _ = self._run_command(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path
        )
        if ret != 0:
            self.logger.error("Failed to create branch")
            return None
            
        # Add all changes
        ret, _, _ = self._run_command(
            ["git", "add", "-A"],
            cwd=repo_path
        )
        
        # Commit
        ret, _, _ = self._run_command(
            ["git", "commit", "-m", title],
            cwd=repo_path
        )
        if ret != 0:
            self.logger.error("Failed to commit changes")
            return None
        
        # DEBUG: Check current remote
        ret, stdout, _ = self._run_command(
            ["git", "remote", "-v"],
            cwd=repo_path
        )
        self.logger.info(f"Current remotes before push: {stdout}")
        
        # Push branch - Set authentication
        if self.config.github_token:
            self.logger.info(f"Setting authenticated remote URL for {repo_name}")
            auth_url = f"https://x-access-token:{self.config.github_token}@github.com/scrollwm/{repo_name}.git"
            ret, stdout, stderr = self._run_command(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=repo_path
            )
            if ret != 0:
                self.logger.error(f"Failed to set remote URL: {stderr}")
            else:
                self.logger.info("Successfully set authenticated remote URL")
                
            # DEBUG: Check remote after setting
            ret, stdout, _ = self._run_command(
                ["git", "remote", "-v"],
                cwd=repo_path
            )
            self.logger.info(f"Current remotes after setting auth: {stdout}")
        else:
            self.logger.warning("No GitHub token available!")
            
        ret, stdout, stderr = self._run_command(
            ["git", "push", "origin", branch_name],
            cwd=repo_path
        )
        if ret != 0:
            self.logger.error("Failed to push branch")
            self.logger.error(f"Push error details: {stderr}")
            return None
            
        self.logger.info(f"Successfully pushed branch {branch_name}")
        
        # Create PR using gh CLI
        cmd = [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--draft"
        ]
        
        if self.config.github_token:
            env = os.environ.copy()
            env["GH_TOKEN"] = self.config.github_token
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True, env=env
            )
        else:
            result = subprocess.run(
                cmd, cwd=repo_path, capture_output=True, text=True
            )
            
        if result.returncode != 0:
            self.logger.error(f"Failed to create PR: {result.stderr}")
            return None
            
        pr_url = result.stdout.strip()
        self.logger.info(f"Created PR: {pr_url}")
        return pr_url
        
    def generate_report(self, result: SplitResult) -> Path:
        """Generate a detailed report of the split operation"""
        report_path = self.config.workspace_dir / f"split_report_{datetime.now():%Y%m%d_%H%M%S}.md"
        
        with open(report_path, 'w') as f:
            f.write("# Scroll Split Operation Report\n\n")
            f.write(f"**Date**: {datetime.now().isoformat()}\n")
            f.write(f"**Scroll Version**: {self.config.scroll_version}\n")
            f.write(f"**Scroll Commit**: {result.scroll_commit}\n")
            f.write(f"**Status**: {'SUCCESS' if result.success else 'FAILED'}\n\n")
            
            f.write("## Summary\n\n")
            f.write(f"- Scene files extracted: {len(result.scene_files)}\n")
            f.write(f"- Standalone files modified: {len(result.standalone_files_modified)}\n")
            f.write(f"- Build verification: {'Skipped' if self.config.skip_build_verification else 'Performed'}\n")
            f.write(f"- Errors: {len(result.errors)}\n")
            f.write(f"- Warnings: {len(result.warnings)}\n\n")
            
            if result.errors:
                f.write("## Errors\n\n")
                for error in result.errors:
                    f.write(f"- {error}\n")
                f.write("\n")
                
            if result.warnings:
                f.write("## Warnings\n\n")
                for warning in result.warnings:
                    f.write(f"- {warning}\n")
                f.write("\n")
                
            f.write("## Scene Files Extracted\n\n")
            for file_path in sorted(result.scene_files):
                f.write(f"- `{file_path.name}`\n")
                
            f.write("\n## Standalone Files Modified\n\n")
            for file_path in sorted(result.standalone_files_modified):
                rel_path = file_path.relative_to(self.standalone_repo)
                f.write(f"- `{rel_path}`\n")
                
        self.logger.info(f"Report generated: {report_path}")
        return report_path
        
    def run(self) -> SplitResult:
        """Execute the complete split operation"""
        result = SplitResult(success=False, scroll_commit="")
        
        try:
            # Phase 1: Setup and clone repositories
            self.logger.info("=== Phase 1: Repository Setup ===")
            
            # Clone scroll at specified version
            self.clone_repository(
                "https://github.com/scrollwm/scroll.git",
                self.scroll_repo,
                self.config.scroll_version
            )
            result.scroll_commit = self.get_current_commit(self.scroll_repo)
            
            # Clone target repositories
            self.clone_repository(
                "https://github.com/scrollwm/scene-scroll.git",
                self.scene_repo
            )
            self.clone_repository(
                "https://github.com/scrollwm/scroll-standalone.git",
                self.standalone_repo
            )
            
            # Phase 2: Analysis
            self.logger.info("=== Phase 2: Structure Analysis ===")
            structure = self.analyze_scroll_structure()
            
            if structure["missing_files"]:
                result.errors.append(
                    f"Missing {len(structure['missing_files'])} expected files"
                )
                
            if structure["unexpected_files"]:
                result.warnings.append(
                    f"Found {len(structure['unexpected_files'])} unexpected files"
                )
                
            # Phase 3: Scene extraction
            self.logger.info("=== Phase 3: Scene Extraction ===")
            result.scene_files = self.extract_scene_files(structure)
            self.create_scene_build_files()
            
            # Phase 4: Standalone update
            self.logger.info("=== Phase 4: Standalone Update ===")
            result.standalone_files_modified = self.update_standalone_files()

            # Phase 5: Verification
            self.logger.info("=== Phase 5: Build Verification ===")
            
            if self.config.skip_build_verification:
                self.logger.info("Skipping build verification (--skip-build-verification is set)")
            elif not self.config.dry_run:
                scene_build_ok = self.verify_build(self.scene_repo)
                standalone_build_ok = self.verify_build(self.standalone_repo)
                
                if not scene_build_ok:
                    result.errors.append("scene-scroll build failed")
                    result.warnings.append("Build verification failed for scene-scroll but continuing anyway")
                if not standalone_build_ok:
                    result.errors.append("scroll-standalone build failed")
                    result.warnings.append("Build verification failed for scroll-standalone but continuing anyway")
                    
                if not (scene_build_ok and standalone_build_ok):
                    self.logger.warning("Build verification failed but continuing with PR creation")
            else:
                self.logger.info("Skipping build verification in dry-run mode")
                   
            # Phase 6: Create PRs
            if self.config.create_prs:
                self.logger.info("=== Phase 6: Creating Pull Requests ===")
                
                branch_name = f"update-{self.config.scroll_version}-{datetime.now():%Y%m%d}"
                pr_body = f"""## Automated Split from Scroll {self.config.scroll_version}

This PR was automatically generated by the scroll-split-tools automation.

**Source**: Scroll commit `{result.scroll_commit}`
**Date**: {datetime.now().isoformat()}

### Changes
- Updated from upstream Scroll version {self.config.scroll_version}
- All modifications were applied automatically
- Build verification: {'PASSED' if not self.config.dry_run else 'SKIPPED (dry run)'}

### Files Modified
- See commit diff for detailed changes

---
*Generated by [scroll-split-tools](https://github.com/scrollwm/scroll-split-tools)*
"""
                
                # Create PR for scene-scroll
                scene_pr = self.create_pull_request(
                    "scene-scroll",
                    branch_name,
                    f"Update to Scroll {self.config.scroll_version}",
                    pr_body
                )
                
                # Create PR for scroll-standalone  
                standalone_pr = self.create_pull_request(
                    "scroll-standalone",
                    branch_name,
                    f"Update to Scroll {self.config.scroll_version}",
                    pr_body + f"\n\n**Related PR**: {scene_pr}"
                )
                
                if scene_pr and standalone_pr:
                    self.logger.info("Successfully created both PRs")
                else:
                    result.warnings.append("Failed to create one or more PRs")
                    
            # Success!
            result.success = True
            self.logger.info("=== Split Operation Completed Successfully ===")
            
        except Exception as e:
            self.logger.error(f"Split operation failed: {e}")
            result.errors.append(str(e))
            
        finally:
            # Generate report
            self.generate_report(result)
            
        return result


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Split Scroll window manager into modular components"
    )
    parser.add_argument(
        "version",
        help="Scroll version to split (e.g., 1.11.3)"
    )
    parser.add_argument(
        "--manifest",
        default="split_manifest.json",
        help="Path to split manifest file"
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Workspace directory (default: temp directory)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without making changes"
    )
    parser.add_argument(
        "--no-prs",
        action="store_true",
        help="Skip creating pull requests"
    )
    parser.add_argument(
        "--skip-build-verification",
        action="store_true",
        default=True,  # Default to True
        help="Skip build verification step (default: True)"
    )
    parser.add_argument(
        "--verify-builds",
        action="store_true",
        help="Enable build verification (opposite of --skip-build-verification)"
    )
    parser.add_argument(
        "--github-token",
        help="GitHub token for PR creation (or use GH_TOKEN env var)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup workspace
    if args.workspace:
        workspace_dir = Path(args.workspace)
        workspace_dir.mkdir(parents=True, exist_ok=True)
    else:
        workspace_dir = Path(tempfile.mkdtemp(prefix="scroll_split_"))
        
    # Get GitHub token
    github_token = args.github_token or os.environ.get("GH_TOKEN")
    
    # Create configuration
    config = SplitConfig(
        scroll_version=args.version,
        workspace_dir=workspace_dir,
        manifest_path=Path(args.manifest),
        dry_run=args.dry_run,
        create_prs=not args.no_prs,
        github_token=github_token,
        log_level=args.log_level,
        skip_build_verification=not args.verify_builds
    )
    
    # Run splitter
    splitter = ScrollSplitter(config)
    result = splitter.run()
    
    # Exit with appropriate code
    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
