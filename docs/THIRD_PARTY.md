# EndoForge third-party components and provenance

The public EndoForge repository contains project source, UE project assets, configuration, and development scripts. It does **not** contain the Unreal Engine installation, SOFA SDK, downloaded header/tool archives, compiled physics runtime, or packaged trainer.

[`Physics/dependencies.json`](../Physics/dependencies.json) is the download manifest: it records URLs, versions, local destinations, and SHA-256 pins. [`Physics/dependency-hashes.json`](../Physics/dependency-hashes.json) retains the recorded checksum inventory using repository-relative paths. Checksums identify downloaded bytes; they are not independent signature verification.

## Dependency inventory

| Component | Version / provenance | Use | Upstream license / notice source |
|---|---|---|---|
| Unreal Engine | 5.7.4, installed separately | UE editor/build tools and renderer | Epic's Unreal Engine license; engine code and installer are not vendored here |
| SOFA | Official Win64 SDK and source tag `v26.06.00`; commit `7c18e95d5c5f2839079892c69e7d89a313c79603` | Dynamically linked FEM, collision, contact, solver, and simulation components | Selected framework/components: LGPL-2.1-or-later; SDK `LICENSE-LGPL.md`, `Authors.txt`, `git-info.txt`, and component/source notices |
| tinyxml2 | Binary bundled with the pinned SOFA SDK | Transitive runtime dependency | zlib license; SDK `licenses/LIBTINYXML2-README.txt` |
| Tight Inclusion | Binary from the pinned SOFA SDK; SDK config reports 1.0.4, SOFA source recipe uses tag `v1.0.6-export-target` | Transitive dependency of collision intersection | MIT; the pinned recipe-tag license is downloaded separately, then staged as `licenses/TIGHT-INCLUSION-MIT.txt` |
| Eigen | 3.4.0 | C++ headers | MPL-2.0 primary license; downloaded `COPYING.MPL2` plus file-level notices |
| Boost | 1.87.0 | C++ headers; no Boost runtime DLL is used | Boost Software License 1.0; `LICENSE_1_0.txt` |
| nlohmann/json | 3.11.3 | C++ JSON protocol header | MIT; `LICENSE.MIT` from the same version tag |
| CMake | 4.4.4 portable Windows distribution | Build only | BSD-3-Clause; distribution contains additional third-party notices |
| Microsoft toolchain and runtime | Validated with MSVC 19.38.33145.0 / Windows SDK 10.0.22621.0 | Native/UE builds and Windows execution | Supplied under Microsoft's terms; installed separately or included through UE's standard prerequisite packaging |

SOFA's complete SDK contains additional components and plugins with their own licenses. Runtime staging selects the libraries needed by this project and their SDK DLL dependencies; this table does not relicense every component present in the full SDK. The integration does not use SofaPython3 or a GPL SofaUE5-Renderer bridge.

Dependency links and checksums are in the manifest rather than duplicated here. The nlohmann/json header and its separately downloaded version-tag license are both hash-pinned. Tight Inclusion's DLL checksum is retained in the checksum inventory and comes from the pinned SDK archive; its separately downloaded license is pinned as well.

## Runtime notices and corresponding source

After a dependency download and physics build, `Physics/stage-runtime.ps1` copies the selected notices and the tracked [`Physics/THIRD-PARTY-NOTICES.txt`](../Physics/THIRD-PARTY-NOTICES.txt) template to `Physics/runtime/licenses/`. It also creates `etc/sofa.ini`, build metadata, and a list of the staged application/DLL files in `runtime-manifest.txt`. These runtime files are generated locally and excluded from Git.

The download step retains the matching SOFA source archive at:

```text
ThirdParty/SOFA/sofa-v26.06.00-source.zip
```

The Phase 2 assembler includes that archive in local deliverables at:

```text
Source/Dependencies/sofa-v26.06.00-source.zip
```

It also includes `Source/Physics`, the UE project source/assets, the selected runtime DLLs, and license notices under `Physics/licenses` and `Licenses`. Keep those notices and the corresponding source with any distribution of the current runtime. Replacing or adding an SDK library requires reviewing that component's own license and source provenance; the existing file list is not a blanket approval for all SDK plugins.

The service dynamically links the SOFA libraries. Build instructions and pinned dependency locations are included so the native service and its dependencies can be rebuilt or replaced. The documented download/build workflow currently uses the official prebuilt SOFA SDK; it does not itself compile the complete SOFA source archive.

## Project assets and project license

The training pad, instrument geometry, materials, and map are created by the project's procedural code/scripts. The original Phase 5 and Phase 6 Blender scenes, exported meshes, textures and anatomy definitions are included with their authoring scripts. These are engineering demonstration assets, not patient scans or clinically certified anatomical models. UE's engine content remains part of the separately installed engine.

Tutor-provided medical imagery, anatomy reference archives and research requirement documents under the local `source/` directory are not republished. Those references informed development direction; this repository does not redistribute their meshes or grant rights to those source materials. The public screenshots show the project's synthetic simulation scene. Project author and maintainer: Avalon (`avalon-lune`).

This document records third-party provenance. It does not assign an MIT license, or any other project-wide license, to the project's original source or assets. Third-party license names above apply to those dependencies.
