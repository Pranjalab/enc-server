# Server Testing Guide

This document explains how to verify the integrity and security of the ENC Server.

## Prerequisites
*   The server must be running locally via Docker (`docker compose up -d`).
*   You must have `pytest` installed (`pip install pytest paramiko`).
*   **Important**: Tests run against `localhost:2222`. Ensure no other service blocks this port.

## Running Tests

From the project root (one level up from here), run:

```bash
pytest -s enc-server/tests/
```

## Test Suites

### 1. `test_ssh.py`
**Goal**: Verify pure SSH connectivity.
*   **Checks**: 
    1.  Admin Login via Password.
    2.  Admin Login via SSH Key (ephemeral generation).
*   **Failure**: Usually indicates SSHD is down or keys are misconfigured.

### 2. `test_rbac.py`
**Goal**: Verify Role-Based Access Control and Restricted Shell boundaries.
*   **Checks**:
    1.  Connects as a restricted user (`developer1`).
    2.  Attempts forbidden commands (`ls`, `cd`). Expects rejection.
    3.  Attempts allowed commands (`enc`, `help`). Expects success.
*   **Failure**: Indicates the restricted shell (`enc-shell`) is not active or Python logic is broken.

### 3. `test_user_lifecycle.py`
**Goal**: Verify User Management Logic.
*   **Checks**:
    1.  **Add**: Creates a new user via `enc user add`.
    2.  **List**: Verifies user appears in the table with correct role.
    3.  **Remove**: Deletes the user.
    4.  **Verify**: Ensures login is impossible after removal.
*   **Failure**: Indicates issues with `sudo` permissions or `policy.json` persistence.
