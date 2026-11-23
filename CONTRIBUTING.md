# Contributing to Solar Fishing

Thank you for your interest in contributing to Solar Fishing.

This document explains how to propose changes, report problems, and help keep the project maintainable across Windows, macOS, and Linux.

## Before you contribute

- **Check the project license.** Solar Fishing is distributed under the AsphaltCake Proprietary License. Read `LICENSE.txt` before submitting or reusing code. Do not assume that the project is open source or that a contribution changes its licensing.
- **Discuss substantial changes first.** For a new feature, major refactor, or change to platform-specific behavior, open an issue or contact the project maintainers before investing significant work.
- **Keep changes focused.** Prefer small pull requests that address one problem and are straightforward to review.
- **Be respectful.** All project spaces and contribution discussions are covered by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs

When opening a bug report, include as much of the following as you can:

- Solar Fishing version (for example, `v2026.11.1`).
- Operating system and version.
- Python version, if running from source.
- A clear description of what you expected and what happened.
- Steps to reproduce the problem.
- Relevant error messages or a traceback.
- Whether the issue happens consistently or intermittently.

Before reporting, check whether the issue has already been reported. **Do not include passwords, access tokens, private account information, or other sensitive data** in reports, logs, or screenshots.

## Suggesting features

Feature suggestions are most useful when they explain:

1. The problem or workflow the feature would improve.
2. The behavior you would expect.
3. Any relevant operating-system differences or limitations.

A suggestion is not a commitment to implement the feature. The maintainers may ask for clarification or decide that it does not fit the project's direction.

## Making code changes

1. Start from the version of the source that matches the issue you are addressing.
2. Keep the change as small and self-contained as practical.
3. Follow the existing code style and naming conventions in the surrounding code.
4. Preserve existing behavior unless the change specifically requires otherwise.
5. Handle platform-specific imports and functionality carefully. Solar Fishing contains Windows-, macOS-, and Linux-specific code paths.
6. Avoid adding dependencies unless they are needed. If you add one, explain why and update `requirements.txt` where appropriate.
7. Do not commit generated files, local settings, personal data, credentials, or unrelated formatting changes.

## Testing

Run the application and test the affected behavior on the platform(s) relevant to your change.

Where applicable, check:

- The application starts successfully.
- The affected feature works as expected.
- Existing behavior in nearby features has not regressed.
- Platform-specific code is only imported or executed on supported platforms.
- Optional dependencies fail gracefully when they are unavailable.

If you cannot test on every relevant operating system, state which operating system and versions you did test on, and identify anything you could not verify. Do not claim that a platform was tested when it was not.

## Submitting a pull request

A useful pull request should include:

- A concise title describing the change.
- The problem being addressed and the approach taken.
- Any related issue or discussion.
- The operating system(s) and environment(s) tested.
- Screenshots or short recordings for GUI changes, when useful.
- Notes about new dependencies, configuration changes, or known limitations.

Keep pull requests focused and be prepared to respond to review feedback. Maintainers may request changes, decline a proposal, or ask for additional testing.

## Dependencies and setup

The Python package dependencies are listed in `requirements.txt`. Some functionality also depends on software installed outside Python, such as the Tesseract OCR executable. Follow the project's setup instructions for your operating system.

The source imports platform-specific libraries, including PyObjC frameworks on macOS, `python-xlib` on Linux, and optional Windows capture/window helpers. A successful `pip install` alone does not guarantee that every platform feature is available.

## Questions

For questions about contributing, use the project's established issue tracker or community support channels. Please do not publish private security or account information in public discussions.
