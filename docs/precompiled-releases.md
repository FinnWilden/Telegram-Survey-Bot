# Preparing and publishing precompiled releases

This repository is prepared to build ZIP packages for Windows, Linux, and
macOS with PyInstaller. The packages bundle Python and the application
dependencies, so users do not need to install Python. Builds run on native
GitHub-hosted runners; they are not cross-compiled.

## Current status

The workflow only runs when a version tag matching `v*.*.*` is pushed. It
runs the test suite first, then builds one package per operating system.
Successful runs upload temporary GitHub Actions artifacts for 30 days.
The workflow does **not** create or publish a GitHub Release. No precompiled
release is published until a maintainer creates one manually.

The macOS package is built for the architecture of GitHub's `macos-latest`
runner. It is not code-signed or notarized. Test it on the target macOS
version before distributing it; Gatekeeper may warn or block it. Supporting
both Intel and Apple silicon, or distributing without Gatekeeper warnings,
requires additional runner/build and Apple signing setup.

## Before the first public build

1. Finish user testing and merge the intended source changes to the release
   branch.
2. Review `config/config.yml` and make sure it contains only the placeholder
   bot token. Never package a live token, study configuration, or database.
3. Run the tests and inspect the packaging workflow on GitHub Actions.
4. Test the resulting packages on clean target machines for each supported
   operating system. Verify startup, configuration loading, Telegram
   connection, logging, database creation, and shutdown.
5. Decide whether the unsigned macOS build is acceptable. If not, configure
   Apple code signing and notarization before publishing a macOS download.

## Build packages

Choose a new semantic version, for example `v1.0.0`. From a clean checkout of
the release branch:

```bash
git pull
git checkout main
git pull
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

Replace `main` if the project uses a different release branch, and choose a
version that has not already been tagged. Pushing the tag starts the
**Build precompiled packages** workflow. In the repository's **Actions** tab,
wait for the test job and all three platform builds to succeed.

Download each ZIP from the completed workflow run's **Artifacts** section.
Workflow artifacts are temporary (30 days) and are not public release assets.
Inspect the archive contents and test each package before publishing.

## Publish a GitHub Release

1. Open the repository's **Releases** page and choose **Draft a new release**.
2. Select the tag that triggered the successful build (for example, `v1.0.0`).
3. Add release notes describing important changes, limitations, and upgrade
   considerations. Do not include participant data or secrets.
4. Upload the three tested ZIP artifacts: Windows, Linux, and macOS.
5. Confirm the correct files and tag, then publish the release.
6. Update the wiki's precompiled-download page to link directly to the new
   release assets and describe any platform-specific warnings.

Publishing is deliberately a manual step: merging a branch does not create
or publish a release. Do not move or reuse a version tag after publishing;
create a new version tag for each release.

## Package contents and user data

Each ZIP contains the PyInstaller application directory, `config/config.yml`
with a placeholder token, empty `db` and `log` directories, the license, and
a packaged README. It intentionally excludes `config/test.*`, the working
database, local logs, virtual environments, and the developer's configuration.
The YAML file is copied into the archive as a separate editable file; it is
not bundled into the executable.

Before the first start, users need to configure either the supplied
`config/config.yml` or a separate YAML/JSON file with their bot token and study
settings. The packaged template has a placeholder token and example URLs, so
it is not ready to run unchanged. Users can edit the supplied file, or pass
another config file as the first command-line argument, for example
`Survey-Bot.exe "C:\study\config.yml"` on Windows or
`./Survey-Bot "/study/config.yml"` on Linux/macOS. Without an argument, the
bot reads the separate `config/config.yml` file beside the executable in the
extracted folder. The config lookup does not depend on the current working
directory. Start the bot from the extracted folder so its database and logs
are stored there as well.

Users must keep the extracted directory together. The database contains
participant state and should be backed up and handled as sensitive study data.
