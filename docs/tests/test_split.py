#!/usr/bin/env python3
"""
test_split.py - Test suite for the Scroll split automation
"""

import unittest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from split_scroll import ScrollSplitter, SplitConfig, SplitResult


class TestManifestValidation(unittest.TestCase):
    """Test manifest file validation"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest_path = Path(self.temp_dir) / "test_manifest.json"
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        
    def test_valid_manifest(self):
        """Test loading a valid manifest"""
        manifest = {
            "version": "1.0.0",
            "scene_files": {
                "implementation": ["sway/tree/scene/scene.c"],
                "headers": ["sway/tree/scene/scene.h"]
            },
            "modifications": {
                "include_patterns": [
                    {"from": "pattern", "to": "replacement"}
                ]
            }
        }
        
        with open(self.manifest_path, 'w') as f:
            json.dump(manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=self.manifest_path
        )
        
        splitter = ScrollSplitter(config)
        self.assertEqual(splitter.manifest["version"], "1.0.0")
        
    def test_missing_manifest(self):
        """Test handling of missing manifest file"""
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=Path("/nonexistent/manifest.json")
        )
        
        with self.assertRaises(RuntimeError):
            ScrollSplitter(config)
            
    def test_invalid_manifest_json(self):
        """Test handling of invalid JSON in manifest"""
        with open(self.manifest_path, 'w') as f:
            f.write("{ invalid json")
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=self.manifest_path
        )
        
        with self.assertRaises(RuntimeError):
            ScrollSplitter(config)


class TestFileOperations(unittest.TestCase):
    """Test file manipulation operations"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manifest = {
            "scene_files": {
                "implementation": ["sway/tree/scene/scene.c"],
                "headers": ["sway/tree/scene/scene.h"]
            },
            "modifications": {
                "include_patterns": [
                    {
                        "from": '#include "sway/tree/scene.h"',
                        "to": '#include <scene-scroll/scene.h>'
                    }
                ]
            }
        }
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        
    def test_include_replacement(self):
        """Test include statement replacement"""
        # Create test file
        test_file = Path(self.temp_dir) / "test.c"
        original_content = '''#include "sway/tree/scene.h"
#include <wlroots/types/wlr_output.h>

void test_function() {
    sway_scene_create();
}
'''
        test_file.write_text(original_content)
        
        # Create config and splitter
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(self.manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path
        )
        
        splitter = ScrollSplitter(config)
        
        # Test replacement
        result = splitter._update_file_includes(test_file)
        self.assertTrue(result)
        
        # Check content
        new_content = test_file.read_text()
        self.assertIn('#include <scene-scroll/scene.h>', new_content)
        self.assertNotIn('#include "sway/tree/scene.h"', new_content)
        
    def test_dry_run_no_modifications(self):
        """Test that dry run doesn't modify files"""
        test_file = Path(self.temp_dir) / "test.c"
        original_content = '#include "sway/tree/scene.h"'
        test_file.write_text(original_content)
        
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(self.manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path,
            dry_run=True
        )
        
        splitter = ScrollSplitter(config)
        splitter._update_file_includes(test_file)
        
        # Content should be unchanged
        self.assertEqual(test_file.read_text(), original_content)


class TestStructureAnalysis(unittest.TestCase):
    """Test repository structure analysis"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scroll_repo = Path(self.temp_dir) / "scroll"
        
        # Create mock Scroll structure
        scene_dir = self.scroll_repo / "sway/tree/scene"
        scene_dir.mkdir(parents=True)
        
        # Create expected files
        (scene_dir / "scene.c").write_text("// scene implementation")
        (scene_dir / "color.c").write_text("// color implementation")
        (scene_dir / "scene.h").write_text("// scene header")
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        
    def test_analyze_structure_success(self):
        """Test successful structure analysis"""
        manifest = {
            "scene_files": {
                "implementation": [
                    "sway/tree/scene/scene.c",
                    "sway/tree/scene/color.c"
                ],
                "headers": ["sway/tree/scene/scene.h"]
            }
        }
        
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path
        )
        
        splitter = ScrollSplitter(config)
        splitter.scroll_repo = self.scroll_repo
        
        structure = splitter.analyze_scroll_structure()
        
        self.assertEqual(len(structure["scene_files"]), 3)
        self.assertEqual(len(structure["missing_files"]), 0)
        self.assertEqual(len(structure["unexpected_files"]), 0)
        
    def test_detect_missing_files(self):
        """Test detection of missing expected files"""
        manifest = {
            "scene_files": {
                "implementation": [
                    "sway/tree/scene/scene.c",
                    "sway/tree/scene/missing.c"  # This doesn't exist
                ],
                "headers": []
            }
        }
        
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path
        )
        
        splitter = ScrollSplitter(config)
        splitter.scroll_repo = self.scroll_repo
        
        structure = splitter.analyze_scroll_structure()
        
        self.assertEqual(len(structure["missing_files"]), 1)
        self.assertEqual(str(structure["missing_files"][0]), "sway/tree/scene/missing.c")
        
    def test_detect_unexpected_files(self):
        """Test detection of unexpected files"""
        # Create an unexpected file
        (self.scroll_repo / "sway/tree/scene" / "unexpected.c").write_text("// unexpected")
        
        manifest = {
            "scene_files": {
                "implementation": ["sway/tree/scene/scene.c"],
                "headers": []
            }
        }
        
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path
        )
        
        splitter = ScrollSplitter(config)
        splitter.scroll_repo = self.scroll_repo
        
        structure = splitter.analyze_scroll_structure()
        
        self.assertGreater(len(structure["unexpected_files"]), 0)
        unexpected_names = [f.name for f in structure["unexpected_files"]]
        self.assertIn("unexpected.c", unexpected_names)


class TestBuildGeneration(unittest.TestCase):
    """Test build file generation"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scene_repo = Path(self.temp_dir) / "scene-scroll"
        self.scene_repo.mkdir()
        
        # Create src directory with files
        src_dir = self.scene_repo / "src"
        src_dir.mkdir()
        (src_dir / "scene.c").write_text("// scene")
        (src_dir / "color.c").write_text("// color")
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

        def test_meson_build_generation(self):
        """Test meson.build file generation"""
        manifest_path = Path(self.temp_dir) / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump({"scene_files": {}}, f)
            
        config = SplitConfig(
            scroll_version="1.11.3",
            workspace_dir=Path(self.temp_dir),
            manifest_path=manifest_path
        )
        
        splitter = ScrollSplitter(config)
        splitter.scene_repo = self.scene_repo
        splitter.create_scene_build_files()
        
        meson_file = self.scene_repo / "meson.build"
        self.assertTrue(meson_file.exists())
        
        content = meson_file.read_text()
        self.assertIn("project('scene-scroll'", content)
        self.assertIn("'src/scene.c'", content)
        self.assertIn("'src/color.c'", content)
        self.assertIn("scene_scroll_dep = declare_dependency", content)


class TestSplitIntegration(unittest.TestCase):
    """Integration tests for the complete split process"""
    
    @patch('split_scroll.ScrollSplitter._run_command')
    @patch('split_scroll.ScrollSplitter.clone_repository')
    def test_full_split_success(self, mock_clone, mock_run):
        """Test successful full split operation"""
        # Setup mocks
        mock_run.return_value = (0, "abc123", "")  # Success
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = {
                "version": "1.0.0",
                "scene_files": {
                    "implementation": [],
                    "headers": []
                },
                "modifications": {
                    "include_patterns": []
                }
            }
            
            manifest_path = Path(temp_dir) / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f)
                
            config = SplitConfig(
                scroll_version="1.11.3",
                workspace_dir=Path(temp_dir),
                manifest_path=manifest_path,
                dry_run=True,
                create_prs=False
            )
            
            splitter = ScrollSplitter(config)
            
            # Create mock repo structures
            for repo in ["scroll", "scene-scroll", "scroll-standalone"]:
                repo_path = Path(temp_dir) / repo
                repo_path.mkdir()
                (repo_path / ".git").mkdir()
                
            # Mock scene directory
            scene_dir = Path(temp_dir) / "scroll/sway/tree/scene"
            scene_dir.mkdir(parents=True)
            
            result = splitter.run()
            
            self.assertTrue(result.success)
            self.assertEqual(len(result.errors), 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""
    
    def test_handle_git_failure(self):
        """Test handling of git command failures"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump({}, f)
                
            config = SplitConfig(
                scroll_version="1.11.3",
                workspace_dir=Path(temp_dir),
                manifest_path=manifest_path
            )
            
            splitter = ScrollSplitter(config)
            
            # Test with non-existent repo
            with self.assertRaises(RuntimeError):
                splitter.clone_repository(
                    "https://github.com/nonexistent/repo.git",
                    Path(temp_dir) / "test"
                )
                
    def test_handle_build_failure(self):
        """Test handling of build failures"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump({}, f)
                
            config = SplitConfig(
                scroll_version="1.11.3",
                workspace_dir=Path(temp_dir),
                manifest_path=manifest_path
            )
            
            splitter = ScrollSplitter(config)
            
            # Create repo with no meson.build
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()
            
            result = splitter.verify_build(repo_path)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
