# 🔧 Interface Sync

> A Clang AST based utility that synchronizes derived class header files when a C++ interface evolves.
> Interface Sync only tracks **pure virtual interface methods** (= 0). Non-pure virtual methods with default implementations are intentionally ignored.

---

## 📌 What Is This Tool

Interface Sync compares:

- 🔹 An **old** interface definition
- 🔹 A **new** interface definition

...and automatically updates derived class header files to match.

### Supported changes

| Change type    | Description                |
| -------------- | -------------------------- |
| ➖ Removed      | Interface method removed   |
| ➕ Added        | Interface method added     |
| 🔁 Parameters  | Method parameter changes   |
| 🔁 Return type | Method return type changes |

> **Design guarantee:** The tool never deletes user declarations. Instead, it removes obsolete `override` specifiers and appends new override stubs.

---

## 🗂️ Project Structure

```text
sync_interface/
│
├── interface_sync.py
├── logger.py
│
└── test/
    │
    ├── include/
    │   ├── IObserver_old.h
    │   └── IObserver.h
    │
    └── src/
        ├── LoggerObserver.h
        ├── NetworkObserver.h
        │
        ├── market/
        │   ├── MarketObserver.h
        │   └── MarketDataManager.h
        │
        └── strategy/
            ├── StrategyObserver.h
            ├── UnrelatedClass.h
            │
            └── alpha/
                ├── AlphaObserver.h
                └── AlphaEngine.h
```

---

## 🧩 Components

### `interface_sync.py` — main executable

- Parse old interface
- Parse new interface
- Detect interface differences
- Recursively scan source directories
- Find classes derived from the target interface
- Remove obsolete override specifiers
- Append new override stubs
- Generate summary report
- Generate log file

### `logger.py` — logging utility

- Output messages to terminal
- Output messages to log file
- Automatically create timestamped log files
- Remove old log files before execution

Example:

```text
interface_sync_20260825_171928.log
```

---

## 🚶 Example Walkthrough

The remainder of this document uses the sample project under `test/`.

### Step 1 — Original Interface

📄 `test/include/IObserver_old.h`

```cpp
class IObserver
{
public:

    virtual ~IObserver() = default;

    virtual void OnConnected() = 0;

    virtual void OnData(int id) = 0;
};
```

### Step 2 — Updated Interface

📄 `test/include/IObserver.h`

```cpp
class IObserver
{
public:

    virtual ~IObserver() = default;

    virtual void OnData(
        int id,
        double timestamp
    ) = 0;

    virtual void OnError(
        int err_code
    ) = 0;
};
```

**Detected changes**

| Type       | Method                                |
| ---------- | ------------------------------------- |
| ❌ Deleted  | `OnConnected()`                       |
| 🔁 Changed | `OnData(int)` → `OnData(int, double)` |
| ✨ Added    | `OnError(int)`                        |

### Step 3 & 5 — Derived Class, Before vs. After Sync

📄 `test/src/LoggerObserver.h`

<table>
<tr>
<th align="left">❌ Before Sync</th>
<th align="left">✅ After Sync</th>
</tr>
<tr>
<td valign="top">

```cpp
class LoggerObserver : public IObserver
{
public:

    void OnConnected() override;

    void OnData(int id) override;
};
```

</td>
<td valign="top">

```cpp
class LoggerObserver : public IObserver
{
public:

    void OnConnected();

    void OnData(int id);

    void OnData(
        int id,
        double timestamp
    ) override;

    void OnError(
        int err_code
    ) override;
};
```

</td>
</tr>
</table>

### Step 4 — Run Interface Sync

**macOS / Linux:**

```bash
python3 interface_sync.py \
    --old test/include/IObserver_old.h \
    --new test/include/IObserver.h \
    --src test/src
```

**Windows:**

```cmd
python interface_sync.py ^
    --old test/include/IObserver_old.h ^
    --new test/include/IObserver.h ^
    --src test/src
```

**Parameters**

| Flag    | Description                               |
| ------- | ----------------------------------------- |
| `--old` | Original interface definition             |
| `--new` | Updated interface definition              |
| `--src` | Root directory containing derived classes |

The tool recursively scans all header files under `test/src`, including nested folders.

### Step 6 — Diff View

```diff
- void OnConnected() override;
+ void OnConnected();

- void OnData(int id) override;
+ void OnData(int id);

+ void OnData(int id, double timestamp) override;
+
+ void OnError(int err_code) override;
```

### Step 7 — Console Output

```text
⚙️ Inspecting Derived Class file: test/src/LoggerObserver.h...

   ⚠️ [DELETED IN BASE]
   'void OnConnected()'
      -> remove override

   ⚠️ [PARAMS CHANGED]
   'void OnData(int id)'
      -> remove override
      + 'void OnData(int id, double timestamp) override'

   ✨ [NEW IN BASE]
   + 'void OnError(int err_code) override'
```

### Step 8 — Summary Output

| Metric            | Count |
| ----------------- | ----- |
| Headers Found     | 8     |
| Derived Classes   | 5     |
| Files Modified    | 5     |
| Overrides Removed | 10    |
| Stubs Added       | 10    |

### Step 9 — Generated Log File

A log file is generated automatically:

```text
interface_sync_20260825_171928.log
```

The log file contains the same information displayed in the terminal.

---

## 🎯 Design Philosophy

The tool never deletes user declarations.

When an interface method is removed or modified:

| Before                          | After                  |
| ------------------------------- | ---------------------- |
| `void OnData(int id) override;` | `void OnData(int id);` |

The declaration remains available for manual refactoring.

New interface methods are appended as **override stubs**, making required changes immediately visible to developers.
