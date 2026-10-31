# 範本：`.github/workflows/ci.yml`

直接採用这个檔案即可；內容只用標準工具與固定環境變數，不需要任何 repository secret。

採用前必做：

1. 把每個 `uses:` 的版本標籤換成完整 40 字元 commit SHA，並保留標籤註解（例：`actions/checkout@<sha>  # v4`）。
2. 若還沒建立 `requirements-dev.txt`，把 G4／G5／G6／G7 四個 job 先註解掉，只上線 G1／G2／G3／G8／G9／G10。
3. 新增 job 一律先掛 `continue-on-error: true`，一週後再開（見 `ROLLOUT.md`）。

```yaml
# .github/workflows/ci.yml
# 提案範本。採用時：所有 uses: 改成完整 commit SHA；先以 continue-on-error 觀察一週。
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

# 最小權限：整個 workflow 只讀。標籤產出另開 workflow 取得 contents: write。
permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

env:
  PYTHONUNBUFFERED: "1"
  PYTHONDONTWRITEBYTECODE: "1"
  PYTHONHASHSEED: "0"
  OPENINBOX_NO_BROWSER: "1"
  TZ: UTC
  PIP_DISABLE_PIP_VERSION_CHECK: "1"
  PIP_NO_INPUT: "1"

jobs:
  # ── G1 語法：最快失敗點 ────────────────────────────────────────────
  syntax:
    name: G1 syntax (py${{ matrix.python }})
    runs-on: ubuntu-24.04
    timeout-minutes: 8
    strategy:
      fail-fast: false
      matrix:
        python: ["3.9", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4          # pin 到完整 SHA
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5      # pin 到完整 SHA
        with:
          python-version: ${{ matrix.python }}
      - name: 位元組碼編譯
        run: python -m compileall -q server fmb_feature2 scripts tests
      - name: 前端 JavaScript 語法（只檢查，不執行）
        if: matrix.python == '3.13'
        run: |
          set -euo pipefail
          for f in ui/modules/*.js ui/pwa/sw.js tests/_tpi_mobile_cdp.js; do
            echo "node --check $f"
            node --check "$f"
          done

  # ── G2 單元測試（Python 3.9 下限；3.13 由 G4 覆蓋）────────────────
  tests:
    name: G2 unittest (py${{ matrix.python }})
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        python: ["3.9"]
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: python -m unittest discover -s tests
        run: |
          set -o pipefail
          python -m unittest discover -s tests 2>&1 | tee "unittest-py${{ matrix.python }}.log"
      - name: 失敗時保留測試日誌
        if: failure()
        uses: actions/upload-artifact@v4   # pin 到完整 SHA
        with:
          name: unittest-log-py${{ matrix.python }}
          path: unittest-py${{ matrix.python }}.log
          retention-days: 7
          if-no-files-found: ignore

  # ── G3 smoke 回歸 ────────────────────────────────────────────────
  smoke:
    name: G3 smoke (Linux)
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: scripts/smoke.sh
        run: |
          set -o pipefail
          bash scripts/smoke.sh 2>&1 | tee smoke.log

  # ── G4 覆蓋率（同時是 Python 3.13 的完整測試）─────────────────────
  coverage:
    name: G4 coverage
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip                        # 需先有 requirements-dev.txt，否則移除本行
          cache-dependency-path: requirements-dev.txt
      - name: 安裝 CI 工具鏈（不進執行期）
        run: python -m pip install -r requirements-dev.txt
      - name: 執行測試並產生覆蓋率
        run: |
          set -o pipefail
          python -m coverage run --branch -m unittest discover -s tests
          python -m coverage report --show-missing
          python -m coverage xml -o coverage.xml
      - name: 覆蓋率門檻（階段 0 為 0；見 GATES.md §3）
        continue-on-error: true             # 階段 2 起移除本行並調整 --fail-under
        run: python -m coverage report --fail-under=0
      - uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage.xml
          retention-days: 14

  # ── G5 lint ─────────────────────────────────────────────────────
  lint:
    name: G5 lint (ruff)
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - name: 安裝 CI 工具鏈
        run: python -m pip install -r requirements-dev.txt
      - name: ruff check
        run: ruff check --output-format=github .
      - name: ruff format（只記錄，不阻擋）
        continue-on-error: true
        run: ruff format --check .

  # ── G6 型別（觀察）──────────────────────────────────────────────
  types:
    name: G6 types (mypy, advisory)
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - name: 安裝 CI 工具鏈
        run: python -m pip install -r requirements-dev.txt
      - name: mypy
        run: |
          set -o pipefail
          mypy 2>&1 | tee mypy.log
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: mypy-report
          path: mypy.log
          retention-days: 7

  # ── G7 相依掃描（只涵蓋 CI 工具鏈）───────────────────────────────
  deps:
    name: G7 dependency audit
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - name: 安裝 CI 工具鏈
        run: python -m pip install -r requirements-dev.txt
      - name: pip-audit
        run: python -m pip_audit -r requirements-dev.txt --strict --progress-spinner off
      - name: pip check
        run: python -m pip check

  # ── G8 秘密掃描（redact；不交給第三方 action）──────────────────────
  secrets:
    name: G8 secret scan
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false        # 掃描不需要 token，也不留憑證
      - name: 取得固定版 gitleaks 並驗證校驗碼
        run: |
          set -euo pipefail
          VER="8.24.0"   # 採用時改成審核過的版本；建議把 SHA256 直接寫死在本檔
          BASE="https://github.com/gitleaks/gitleaks/releases/download/v${VER}"
          curl -sSfL "${BASE}/gitleaks_${VER}_linux_x64.tar.gz" -o /tmp/gitleaks.tgz
          curl -sSfL "${BASE}/gitleaks_${VER}_checksums.txt" -o /tmp/gitleaks.sums
          ( cd /tmp && grep " gitleaks_${VER}_linux_x64.tar.gz$" gitleaks.sums | sha256sum -c - )
          tar -xzf /tmp/gitleaks.tgz -C /tmp gitleaks
          /tmp/gitleaks version
      - name: 掃描工作目錄（不含 git 歷史；歷史掃描在 nightly）
        run: /tmp/gitleaks detect --no-git --redact --no-banner --config .gitleaks.toml --source .

  # ── G9 repo 政策守門 ────────────────────────────────────────────
  policy:
    name: G9 repo policy guard
    needs: syntax
    runs-on: ubuntu-24.04
    timeout-minutes: 8
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: python scripts/ci/policy_guard.py
        run: python scripts/ci/policy_guard.py

  # ── G10 建置與啟動 ──────────────────────────────────────────────
  package:
    name: G10 package + startup
    needs: [tests, smoke]
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: 建立可重現的來源壓縮檔
        run: |
          set -euo pipefail
          mkdir -p "$RUNNER_TEMP/out"
          NAME="openinbox-${GITHUB_SHA:0:12}"
          git archive --format=tar.gz --prefix="${NAME}/" -o "$RUNNER_TEMP/out/${NAME}.tar.gz" HEAD
          ( cd "$RUNNER_TEMP/out" && sha256sum "${NAME}.tar.gz" > SHA256SUMS )
          cat "$RUNNER_TEMP/out/SHA256SUMS"
      - name: 乾淨目錄安裝、啟動、健康檢查
        run: |
          set -euo pipefail
          TMP="$(mktemp -d)"
          tar -xzf "$RUNNER_TEMP/out/"openinbox-*.tar.gz -C "$TMP"
          cd "$TMP"/openinbox-*
          ./install.sh > /dev/null
          PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
          OPENINBOX_NO_BROWSER=1 OPENINBOX_PORT="$PORT" python3 server/app.py > "$TMP/server.log" 2>&1 &
          PID=$!
          trap 'kill "$PID" 2>/dev/null || true' EXIT
          ok=""
          for _ in $(seq 1 40); do
            if curl -fsS "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then ok=1; break; fi
            sleep 0.5
          done
          if [ -z "$ok" ]; then
            echo "伺服器未在 20 秒內就緒"
            sed -n '1,80p' "$TMP/server.log"
            exit 1
          fi
          curl -fsS "http://127.0.0.1:$PORT/api/features" > /dev/null
          echo "startup ok"
      - uses: actions/upload-artifact@v4
        with:
          name: openinbox-source
          path: |
            ${{ runner.temp }}/out/*.tar.gz
            ${{ runner.temp }}/out/SHA256SUMS
          retention-days: 14
```

## 注意事項

- `runner.temp` 在 `upload-artifact` 的 `path` 需要 `${{ runner.temp }}` 展開；若覺得可讀性差，改成先 `cp` 到 `$GITHUB_WORKSPACE/out/` 再上傳（但 `out/` 已在 `.gitignore` 之外，請確認不要被 commit）。
- G4／G5／G6／G7 都需要 `requirements-dev.txt`；沒有這個檔案時 `cache: pip` 這一行也會失敗，務必一起建立或一起移除。
- G8 的 gitleaks 版本號與 checksum 檔都必須在同一個 PR 內更新，且版本升級要人工核對 release notes。
- G10 的啟動檢查會寫 `accounts.json`（由 `install.sh` 從範例複製），全程在 `mktemp -d` 內，不影響 repo。
