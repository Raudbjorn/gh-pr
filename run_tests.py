#!/usr/bin/env python3
"""Test runner script for gh-pr Phase 4 tests."""

import argparse
import subprocess
import sys
from pathlib import Path


def run_tests(test_type="all", verbose=False, coverage=False, parallel=False, marker=None):
    """
    Run tests with specified configuration.

    Args:
        test_type: Type of tests to run (all, unit, integration, phase4)
        verbose: Enable verbose output
        coverage: Enable coverage reporting
        parallel: Enable parallel test execution
        marker: Specific pytest marker to run
    """
    cmd = [sys.executable, "-m", "pytest"]

    # Add test paths based on type
    if test_type == "unit":
        cmd.append("tests/unit/")
    elif test_type == "integration":
        cmd.append("tests/integration/")
    elif test_type == "phase4":
        cmd.extend(["-m", "phase4"])
    elif test_type == "all":
        cmd.append("tests/")

    # Add marker filter if specified
    if marker:
        cmd.extend(["-m", marker])

    # Add verbosity
    if verbose:
        cmd.append("-vv")
    else:
        cmd.append("-v")

    # Add coverage
    if coverage:
        cmd.extend([
            "--cov=src/gh_pr",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml"
        ])

    # Add parallel execution
    if parallel:
        try:
            import pytest_xdist
            cmd.extend(["-n", "auto"])
        except ImportError:
            print("Warning: pytest-xdist not installed, running tests sequentially")

    # Additional options
    cmd.extend([
        "--tb=short",
        "--color=yes",
        "--durations=10"
    ])

    print(f"Running command: {' '.join(cmd)}")
    print("-" * 70)

    try:
        # Security: cmd list is built from static strings and constrained argparse choices
        # No user input is passed directly to the shell (list form prevents injection)
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 130
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(description="Run gh-pr Phase 4 tests")

    parser.add_argument(
        "test_type",
        nargs="?",
        default="all",
        choices=["all", "unit", "integration", "phase4"],
        help="Type of tests to run (default: all)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Enable coverage reporting"
    )

    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)"
    )

    parser.add_argument(
        "-m", "--marker",
        help="Run tests with specific marker (e.g., 'graphql', 'batch', 'export')"
    )

    parser.add_argument(
        "--fast",
        action="store_true",
        help="Run only fast tests (exclude slow and network tests)"
    )

    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install test dependencies before running tests"
    )

    args = parser.parse_args()

    # Install dependencies if requested
    if args.install_deps:
        print("Installing test dependencies...")
        # Install test dependencies from pyproject.toml
        try:
            # Security: Using list form prevents shell injection
            # The package spec ".[test]" is a static string, not user input
            install_cmd = [sys.executable, "-m", "pip", "install", "-e", ".[test]"]
            subprocess.run(install_cmd, check=True)
            print("✓ Installed test dependencies from pyproject.toml")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install test dependencies: {e}")
            print("You can install them manually with: pip install -e '.[test]'")
            return 1

        print("Dependencies installation complete.\n")

    # Handle fast test option
    marker = args.marker
    if args.fast:
        marker = "not slow and not network"

    # Run tests
    exit_code = run_tests(
        test_type=args.test_type,
        verbose=args.verbose,
        coverage=args.coverage,
        parallel=args.parallel,
        marker=marker
    )

    # Print summary
    if exit_code == 0:
        print("\n" + "=" * 70)
        print("🎉 All tests passed!")
        if args.coverage:
            print("📊 Coverage report generated in htmlcov/index.html")
    else:
        print("\n" + "=" * 70)
        print("❌ Some tests failed or there were errors")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())