# Phase 3: Shadow Workspace Implementation Plan

This phase implements the isolated execution environment where Aider operates. The shadow workspace engine reconciles the user's unsaved in-memory buffers with filesystem-backed operations by synchronizing a local copy of the project, running the agent in a shallow Git sandbox, and safely generating diffs for user review.

---

## 1. Shadow Workspace Initialization & Materialization

The daemon must safely create and maintain an isolated project copy without interfering with the user's actual filesystem or Git history.

### Requirements

* Create the V1 shadow workspace root at `.git/alchemist/shadow`.


* Map each project root to one active shadow workspace.


* Implement a full filesystem copy of the project into the shadow workspace.


* Handle large repositories identically to small repositories for V1, deferring performance optimizations.


* Follow Aider behavior for ignore rules, including `.gitignore`, `.aiderignore`, and binary file exclusion.
* Preserve Aider-compatible repo-map inclusion and file-selection behavior; reuse Aider's ignore helpers when they are reliable.

* Maintain a separate Git repository within the shadow workspace. This shallow Git sandbox allows Aider to utilize Git history and repo map mechanics without mutating the real repository history.



### Deliverables

* `ShadowManager` class responsible for workspace directory creation and validation.
* Filesystem cloning routines that correctly parse and honor ignore rules.
* Git sandbox initialization logic (e.g., `git init` within the shadow root).
* Tests verifying correct exclusion of ignored files and isolation from the parent `.git` directory.

---

## 2. Pre-Flight Synchronization

Before the agent executes, the Lua client's live buffer state must overwrite the filesystem copy inside the shadow workspace.

### Requirements

* Before `agent/submit_prompt`, capture the active file list, relevant buffer contents, buffer file paths, SHA-256 content hashes, and modified state from the client.


* Write the provided in-memory buffer contents into the shadow workspace before invoking Aider.


* Ensure unsaved file handling mirrors `aider.nvim` behavior as closely as practical.



### Deliverables

* `PreFlightSync` module to parse incoming buffer payloads from the JSON-RPC request.
* Utilities to hash buffer contents and store them for future validation.
* Overwrite mechanisms to safely update the shadow workspace with live buffer data.
* Tests confirming that modified buffers successfully overwrite stale filesystem files in the shadow tree prior to execution.

---

## 3. Execution Orchestration & Git Diff Generation

With the shadow workspace synchronized, the daemon must execute the assistant engine and capture the resulting file mutations as a unified diff.

### Requirements

* Execute Aider within the isolated shadow workspace copy.


* Following Aider execution and shadow git commit/mutation, calculate a unified diff from the shadow repository.


* Use `git diff HEAD~1` as the preferred method for generating the unified diff.


* Package the generated diff and the captured `base_hashes` into the `ui/diff_ready` JSON-RPC notification payload.



### Deliverables

* Integration hooks wiring the `AssistantEngine` to execute within the designated shadow root path.
* `DiffGenerator` utility responsible for executing Git diff commands and parsing the output.
* Payload formatter for `ui/diff_ready` to ensure valid JSON-RPC dispatch to the Lua client.
* Tests simulating agent file mutations and validating the accuracy of the generated diff strings.
* Verify multi-file changes and file operations represented by the diff, including file creation, rename, deletion, and mode changes.
* Prefer an Aider-native diff API when it is available and reliable; otherwise use `git diff HEAD~1`.

---

## 4. Diff Lifecycle: Acceptance, Rejection, & Optimistic Locking

The engine must safely apply or discard changes based on user input, ensuring live buffers are never corrupted by out-of-sync patches.

### Requirements

* Implement optimistic locking: before applying a returned diff, recompute live buffer hashes and compare them against the `base_hashes` provided in the diff payload.


* If hashes differ, open native diff/conflict resolution mode or notify the user.


* Ensure patch application is transactional at the client layer.


* Snapshot all affected live buffers before applying changes and record cursor/window state where practical. If any file fails to apply, restore all modified buffers from snapshots, avoid partial disk writes, and emit the `PATCH_APPLY_FAILED` error with a remediation hint.
* Apply patches in this priority order: Aider-native mechanism when available and safe; otherwise `git apply` against a temporary index/worktree; otherwise Lua-side buffer patching as a fallback.
* Support multi-file diff review and full-diff application in V1; hunk-level application is optional when provided by the selected diff UI and is not a custom V1 requirement.
* Follow Aider behavior for file creation, rename, deletion, and mode changes, falling back to `git apply` semantics where practical.


* On rejection, rewind the shadow workspace, preferring Aider-native undo behavior or falling back to `git reset --hard HEAD~1`.


* On acceptance, update the shadow baseline after the client confirms the patch was successfully applied and written to disk.


* Clean all V1 shadow workspaces on daemon exit.



### Deliverables

* `AcceptanceFlow` and `RejectionFlow` handlers within the daemon to update the shadow baseline or rewind the sandbox.
* Lua client-side transactional apply logic, including snapshotting, hash verification, and restoration of cursor/window state where practical.
* Daemon shutdown hooks integrated with the Phase 2 `LifecycleManager` to permanently delete `.git/alchemist/shadow` upon exit.
* Tests covering exact hash matches, simulated hash mismatches (conflicts), atomic rollback on partial apply failures, and multi-file/file-operation patches.

---

## 5. Suggested File Layout

Building upon the Phase 2 daemon structure, add the following modules to support Phase 3:

```text
alchemist/
  daemon/
    # (Phase 2 files...)
  workspace/
    __init__.py
    manager.py              # ShadowManager: project copy, git sandbox init
    sync.py                 # PreFlightSync: buffer extraction and overwriting
    diff.py                 # DiffGenerator: git diff HEAD~1 generation
    lifecycle.py            # Accept/Reject handlers, baseline updates, reset logic
    ignore.py               # Aider-compatible ignore/file-selection handling
  engine/
    # (Phase 2 files...)
tests/
  workspace/
    test_manager.py
    test_sync.py
    test_diff_generation.py
    test_accept_reject.py
    test_transactional_apply.py
    test_file_operations.py

```

---

## 6. Phase 3 Acceptance Criteria

Phase 3 is complete when:

* A full filesystem copy is successfully initialized at `.git/alchemist/shadow` when a project is mapped.


* Unsaved buffer contents sent via `agent/submit_prompt` correctly overwrite their corresponding files in the shadow workspace before execution.


* The daemon correctly generates a unified diff (`git diff HEAD~1`) from the shadow repository after a simulated Aider edit.


* Optimistic locking successfully blocks patch application if a live buffer's SHA-256 hash has changed since pre-flight sync.


* Rejecting a diff correctly triggers a `git reset --hard HEAD~1` (or equivalent) in the shadow workspace.


* Accepting a diff correctly updates the shadow workspace baseline to match the applied patch.


* A failed patch application transactionally rolls back all live buffers to their pre-apply snapshots, avoids partial disk writes, and emits `PATCH_APPLY_FAILED` with a remediation hint.


* Multi-file diffs and Aider-style file operations (create, rename, delete, and mode change) are represented and applied correctly through the selected patch path.


* The daemon successfully deletes the `.git/alchemist/shadow` directory upon clean shutdown.
