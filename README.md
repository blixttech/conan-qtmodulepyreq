# Base recipe for building Qt modules

Conan provides a convenient way to reuse recipes via ["Python requires"](https://docs.conan.io/en/latest/extending/python_requires.html) feature.
This repository contains a base conan recipe, ``QtModuleConanBase``, for building Qt modules.
Following shows the usage of ``QtModuleConanBase`` for building ``qtserialport`` Qt module. 

```python
from conans import ConanFile, tools

class QtSerialPortConan(ConanFile):
    name = "qtserialport"
    description = "Serial port module for Qt"
    topics = ("conan", "qtserialport", "serialport")
    url = "https://github.com/blixttech/conan-qtserialport.git"
    homepage = "https://code.qt.io/cgit/qt/qtserialport.git"
    license = "	LGPL-3.0-only"

    python_requires = "qtmodulepyreq/0.1.0"
    python_requires_extend = "qtmodulepyreq.QtModuleConanBase"

    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False]}
    default_options = {"shared": True}
```

Note that ``QtModuleConanBase`` uses [bincrafters Qt builds](https://bintray.com/beta/#/bincrafters/public-conan/qt:bincrafters) by default. 
If a different Qt build is used override ``requirements()`` function in the recipe.