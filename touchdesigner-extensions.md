# TouchDesigner Extensions — Reference Guide

> Source: https://docs.derivative.ca/Extensions  
> Last updated: October 28, 2025

## Overview

**Extensions** allow you to add custom Python data and functionality to a TouchDesigner Component, including support for TouchDesigner's procedural (dependency) system. Extensions are specified as a list of Python objects on the **Extensions page** of a Component.

Each extension can be accessed by other operators either:
- Directly, via **Promotion**
- Through the `ext` object

---

## Creating Extensions

### Via Component Editor (Recommended)

1. Right-click your Component → **Customize Component...**
2. Open the **Extension Code** section
3. Enter the extension name and click **Add**

> **Convention:** Capitalize the extension name and add the suffix `Ext` (e.g., `ColorExt`, `AudioExt`).

### Via Extension Parameters (Manual)

Each component supports up to **4 extensions**, each with 3 parameters:

| Parameter | Description |
|---|---|
| **Extension Object** | Python code that **returns a Python object** when executed. Typically: `ExampleExt(me)` |
| **Extension Name** | Optional custom name. Defaults to the class name. |
| **Promote Extension** | If enabled, capitalized members are accessible directly on the operator. |
| **Re-Init Extensions** | Manually re-runs the Extension Object code and replaces the component's extensions. |

---

## Writing Extension Code

### Default Extension Template

```python
from TDStoreTools import StorageManager
import TDFunctions as TDF

class DefaultExt:
    """
    DefaultExt description
    """
    def __init__(self, ownerComp):
        # The component to which this extension is attached
        self.ownerComp = ownerComp

        # Dependable property (read-write)
        TDF.createProperty(self, 'MyProperty', value=0, dependable=True, readOnly=False)

        # Attributes:
        self.a = 0       # not promoted (lowercase)
        self.B = 1       # promoted (uppercase)

        # Stored items (persistent across saves and re-initialization):
        storedItems = [
            {'name': 'StoredProperty', 'default': None, 'readOnly': False,
             'property': True, 'dependable': True},
        ]
        # Uncomment to activate:
        # self.stored = StorageManager(self, ownerComp, storedItems)

    def myFunction(self, v):
        debug(v)

    def PromotedFunction(self, v):  # promoted because it's capitalized
        debug(v)
```

---

### Importing Modules

```python
from TDStoreTools import StorageManager
import TDFunctions as TDF
```

---

### Python Attributes

Standard Python attributes. Created in `__init__`:

```python
self.ownerComp = ownerComp  # required — the owning component
self.a = 0                  # not promoted (lowercase)
self.B = 1                  # promoted (uppercase)
```

- **Promoted** if name starts with **uppercase** → accessible via `op('myComp').B`
- **Not promoted** if lowercase → internal use only

---

### Python Properties

Use `TDF.createProperty` for dependable properties:

```python
# Read-write dependable property
TDF.createProperty(self, 'MyProperty', value=0, dependable=True, readOnly=False)

# Read-only dependable property
TDF.createProperty(self, 'MyProperty', value=0, dependable=True, readOnly=True)
```

**Reading:**
```python
value = self.MyProperty
```

**Writing (read-only):**
```python
self._MyProperty.val = newValue   # use underscore prefix
```

**Writing (read-write):**
```python
self.MyProperty = newValue
```

---

### Storage Manager

Use `StorageManager` for values that persist across saves and re-initialization:

```python
storedItems = [
    {'name': 'MyValue', 'default': 0, 'readOnly': False, 'property': True, 'dependable': True},
]
self.stored = StorageManager(self, ownerComp, storedItems)
```

> **Tip:** Prefer [Custom Parameters](https://docs.derivative.ca/Custom_Parameters) for values users should see on the parameter page. Use `StorageManager` to hide or internally manage values.

**Setting a stored read-only value:**
```python
self.stored['MyValue'] = newValue
```

See: [StorageManager Class](https://docs.derivative.ca/StorageManager_Class)

---

### Extension Functions

Defined like regular Python class methods:

```python
def myFunction(self, v):        # not promoted
    debug(v)

def PromotedFunction(self, v):  # promoted (capitalized)
    debug(v)
```

Use `self.ownerComp` to access the component from within functions.

---

## Dependable Values

Dependable values automatically update Parameter Expressions that reference them.

- Created via `TDF.createProperty(..., dependable=True)` or `StorageManager`
- For collections (lists, dicts, sets), see [Deeply Dependable Collections](https://docs.derivative.ca/TDStoreTools#Deeply_Dependable_Collections)

---

## Accessing Extensions

### 1. Promotion (Most Common)

If promoted, capitalized members are available directly on the operator:

```python
op('myCustomComp').B
op('myCustomComp').MyProperty
op('myCustomComp').PromotedFunction('test')
```

Non-capitalized members are **not** accessible via promotion:
```python
op('myCustomComp').a              # ❌ not promoted
op('myCustomComp').myFunction()   # ❌ not promoted
```

---

### 2. The `ext` Member

Access any member (promoted or not) via the `ext` member. Searches **up the network hierarchy**:

```python
op('myCustomComp').ext.ExampleExt.B
op('myCustomComp').ext.ExampleExt.a           # works even if not promoted
op('myCustomComp').ext.ExampleExt.myFunction('test')
```

From inside the component (any child operator):
```python
me.ext.ExampleExt.myFunction('test')
ext.ExampleExt.myFunction('test')   # 'me' optional
ext.a                                # in a parameter expression
```

---

### 3. The `extensions` Member

Direct list access (rarely needed):

```python
op('myCustomComp').extensions[0].myFunction('test')
```

---

## Extension Gotchas

### "Cannot use an extension during its initialization"

**Cause:** Something tries to access an extension while `__init__` is still running.

**Fix 1 — In parameter expressions**, use `extensionsReady`:
```python
parent().MyExtensionProperty if parent().extensionsReady else 0
```

**Fix 2 — In extension code**, use `onInitTD`:
```python
def onInitTD(self):
    """Called at end of frame that this extension is initialized."""
    debug('onInitTD')
```

> If multiple extensions initialize on the same frame, all `__init__` functions run before any `onInitTD` functions.

---

### Extensions Staying in Memory After Re-Init

**Cause:** Python garbage collection won't free the extension if another object holds a reference to it.

**Fix:** Use `onDestroyTD` to clean up:

```python
class TestExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.selfRef = self.__init__  # creates self-reference (prevents GC)

    def onDestroyTD(self):
        self.selfRef = None  # remove reference to allow GC

    def __del__(self):
        debug('__del__', self)
```

> `onDestroyTD` is called by TouchDesigner when extensions are re-initialized, unlike `__del__` which may never be called if references exist.

---

## Example: `ColorExt`

A complete extension that stores a base color and cycles through a list.

```python
from TDStoreTools import StorageManager
TDF = op.TDModules.mod.TDFunctions

class ColorExt:
    """
    Stores a base color used by operators inside the component.
    """

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

        # Available colors [R, G, B]
        self.baseColorList = [
            [1, 0, 0],  # red
            [0, 1, 0],  # green
            [0, 0, 1],  # blue
            [1, 1, 1],  # white
        ]

        # Persistent index (survives re-init and save/load)
        storedItems = [
            {'name': 'ColorIndex', 'default': 0, 'readOnly': True},
        ]
        self.stored = StorageManager(self, ownerComp, storedItems)

        # Dependable, read-only property
        TDF.createProperty(self, 'BaseColor',
                           value=self.baseColorList[self.ColorIndex],
                           readOnly=True,
                           dependable=True)

    def IncrementBaseColor(self):
        """Cycle to the next base color."""
        self.stored['ColorIndex'] += 1
        if self.ColorIndex == len(self.baseColorList):
            self.stored['ColorIndex'] = 0
        self._BaseColor.val = self.baseColorList[self.ColorIndex]
```

### Using `BaseColor` in a Parameter Expression

Inside `colorExample`, on a child Container COMP's Background Color:
```python
ext.ColorExt.BaseColor[0]  # Red channel
ext.ColorExt.BaseColor[1]  # Green channel
ext.ColorExt.BaseColor[2]  # Blue channel
```

### Calling `IncrementBaseColor`

From Textport or a script:
```python
op('/path/to/colorExample').IncrementBaseColor()
```

---

## Quick Reference

| Concept | Access Pattern |
|---|---|
| Promoted member | `op('myComp').MyMember` |
| Via `ext` (any member) | `op('myComp').ext.MyExt.myMember` |
| Via `ext` from inside | `ext.MyExt.myMember` or `me.ext.MyExt.myMember` |
| Via `extensions` list | `op('myComp').extensions[0].myMember` |
| Set read-only property | `self._MyProp.val = value` |
| Set stored read-only | `self.stored['MyKey'] = value` |
| Delay until ready | `parent().MyProp if parent().extensionsReady else 0` |
| Post-init callback | `def onInitTD(self): ...` |
| Pre-destroy callback | `def onDestroyTD(self): ...` |

---

## Related Links

- [Component Editor Dialog](https://docs.derivative.ca/Component_Editor_Dialog)
- [StorageManager Class](https://docs.derivative.ca/StorageManager_Class)
- [TDStoreTools — Deeply Dependable Collections](https://docs.derivative.ca/TDStoreTools#Deeply_Dependable_Collections)
- [Custom Parameters](https://docs.derivative.ca/Custom_Parameters)
- [Dependency Class](https://docs.derivative.ca/Dependency_Class)
- [Introduction to Python in TouchDesigner](https://docs.derivative.ca/Introduction_to_Python_Tutorial)
- [Lister Custom COMP](https://docs.derivative.ca/Palette:lister)
- [PopMenu Custom COMP](https://docs.derivative.ca/Palette:popMenu)
