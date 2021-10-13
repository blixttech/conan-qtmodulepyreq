from conans import ConanFile, tools, VisualStudioBuildEnvironment
from conans.tools import cpu_count
from conans.errors import ConanException
from distutils.spawn import find_executable
import os
import re
import glob
import pathlib


class QtModuleConanBase(object):

    module_name = None
    libs = []

    def set_version(self):
        if not self.version:
            git_ref = os.getenv("CONAN_GIT_REF")
            if not git_ref or git_ref == "":
                git = tools.Git(folder=self.recipe_folder)
                git_ref = git.run("describe --all").splitlines()[0].strip()

            self.version = re.sub("^.*/v?|^v?", "", git_ref)

    def requirements(self):
        self.requires("qt/%s" % self.version)

    def configure(self):
        if self.options.shared:
            self.options["qt"].shared = True
        else:
            self.options["qt"].shared = False

    def source(self):
        source_folder = os.path.join(self.source_folder, self.name)
        git = tools.Git(folder=source_folder)
        git.clone(("https://code.qt.io/qt/%s.git" % self.name), "v" + self.version)

    def _fix_vs_build_env(self, build_env):
        if "_LINK_" in build_env:
            build_env["_LINK_"] = re.sub("-ENTRY:mainCRTStartup", "", build_env["_LINK_"])
        return build_env

    def build(self):
        source_folder = os.path.join(self.source_folder, self.name)
        build_folder = os.path.join(self.build_folder, ("%s-build" % self.name))
        install_folder = os.path.join(self.build_folder, ("%s-install" % self.name))

        if not os.path.exists(build_folder):
            os.mkdir(build_folder)
        if not os.path.exists(install_folder):
            os.mkdir(install_folder)

        qmake_pro_file = os.path.join(source_folder, ("%s.pro" % self.name))
        qmake_command = os.path.join(self.deps_cpp_info['qt'].rootpath, "bin", "qmake")
        qmake_args = []

        if self.options.shared:
            qmake_args.append("CONFIG+=shared")
        else:
            qmake_args.append("CONFIG+=staticlib")

        if self.settings.build_type == "Release":
            qmake_args.append("CONFIG+=release")
        elif self.settings.build_type == "Debug":
            qmake_args.append("CONFIG+=debug")
        else:
            raise ConanException("Invalid build type")

        qmake_args.append("-r %s" % qmake_pro_file)

        build_args = []
        if self.settings.os == "Windows":
            build_command = find_executable("jom.exe")
            if not build_command:
                build_command = "nmake.exe"
            else:
                build_args.append("-j")
                build_args.append(str(cpu_count()))
        else:
            build_command = find_executable("make")
            if not build_command:
                raise ConanException("Cannot find make")
            else:
                build_args.append("-j")
                build_args.append(str(cpu_count()))

        if self.settings.os == "Windows":
            # INSTALL_ROOT environmental variable is placed just after the drive part
            # and before the  Qt installation directory in the path.
            # Eg. C:$(INSTALL_ROOT)\.conan\3feb31\1\....
            tail = os.path.splitdrive(install_folder)[1]
            build_args.append("INSTALL_ROOT=" + tail)
        else:
            # INSTALL_ROOT environmental variable is prefixed to the Qt installation directory
            # in the path.
            # Eg. $(INSTALL_ROOT)/home/conan/.conan/data/qt/....
            build_args.append("INSTALL_ROOT=" + install_folder)
        build_args.append("install")

        self.output.info("QMAKE: %s %s" % (qmake_command, " ".join(qmake_args)))
        self.output.info("BUILD: %s %s" % (build_command, " ".join(build_args)))

        if self.settings.compiler == "Visual Studio":
            env_build = VisualStudioBuildEnvironment(self)
            build_env_vars = self._fix_vs_build_env(env_build.vars)
            with tools.environment_append(build_env_vars):
                vcvars_cmd = tools.vcvars_command(self.settings)
                self.run("%s && %s %s" % (vcvars_cmd, qmake_command, " ".join(qmake_args)),
                         cwd=build_folder)
                self.run("%s && %s %s" % (vcvars_cmd, build_command, " ".join(build_args)),
                         cwd=build_folder)
        else:
            self.run("%s %s" % (qmake_command, " ".join(qmake_args)), cwd=build_folder)
            self.run("%s %s" % (build_command, " ".join(build_args)), cwd=build_folder)

    def get_lib_suffix(self):
        if self.settings.build_type == "Debug":
            if self.settings.os == "Windows":
                return "d"
            elif tools.is_apple_os(self.settings.os):
                return "_debug"
        return ""

    def package(self):
        install_folder = os.path.join(self.build_folder, ("%s-install" % self.name))
        # Try to find the location where the files are installed.
        folders = glob.glob(os.path.join(install_folder, "**", ".conan", "**", "include"),
                            recursive=True)
        if len(folders) == 0:
            raise ConanException("Cannot find installation directory")

        install_prefix = pathlib.Path(folders[0]).parent
        self.output.info("install_prefix: %s" % install_prefix)

        self.copy("*", src=install_prefix, symlinks=True)

        # Remove CMake find/config files in favor of using cmake_find_package_multi
        # Refer https://github.com/conan-io/conan-center-index/blob/master/docs/faqs.md#why-are-cmake-findconfig-files-and-pkg-config-files-not-packaged
        for mask in ["Find*.cmake", "*Config.cmake", "*-config.cmake"]:
            tools.remove_files_by_mask(self.package_folder, mask)

        tools.remove_files_by_mask(os.path.join(self.package_folder, "lib"), "*.la*")
        tools.remove_files_by_mask(os.path.join(self.package_folder, "lib"), "*.pdb*")
        tools.remove_files_by_mask(os.path.join(self.package_folder, "bin"), "*.pdb")

        # Find relative path for include, lib and bin folders
        folders = glob.glob(os.path.join(self.package_folder, "**", "include"), recursive=True)
        if len(folders):
            include_base = os.path.relpath(folders[0], self.package_folder)
        else:
            include_base = "include"

        folders = glob.glob(os.path.join(self.package_folder, "**", "lib"), recursive=True)
        if len(folders):
            lib_base = os.path.relpath(folders[0], self.package_folder)
        else:
            lib_base = "lib"

        folders = glob.glob(os.path.join(self.package_folder, "**", "bin"), recursive=True)
        if len(folders):
            bin_base = os.path.relpath(folders[0], self.package_folder)
        else:
            bin_base = "bin"

        # qmake loads Qt modules in <QT_INSTALL_ARCHDATA>/mkspecs/features/qt_config.prf file.
        # In this file, QMAKEMODULES environmental variable is searched for additional module directories.
        # As we build modules seperately, we have to adjust the correct paths in the module's
        # .pri files.
        # So, we use an uniq environmental variable for each module to specify the package path.
        for filename in glob.glob(os.path.join(self.package_folder, "**", "modules", "**", "*.pri"),
                                  recursive=True):
            tools.replace_path_in_file(filename,
                                       "$$QT_MODULE_INCLUDE_BASE",
                                       os.path.join(
                                           "$$(CONAN_PKG_DIR_" + self.name.upper() + ")",
                                           include_base),
                                       strict=False)
            tools.replace_path_in_file(filename,
                                       "$$QT_MODULE_LIB_BASE",
                                       os.path.join(
                                           "$$(CONAN_PKG_DIR_" + self.name.upper() + ")", lib_base),
                                       strict=False)
            tools.replace_path_in_file(filename,
                                       "$$QT_MODULE_BIN_BASE",
                                       os.path.join(
                                           "$$(CONAN_PKG_DIR_" + self.name.upper() + ")", bin_base),
                                       strict=False)

    def package_info(self):
        self.cpp_info.names["cmake_find_package"] = self.module_name
        self.cpp_info.names["cmake_find_package_multi"] = self.module_name
        self.cpp_info.libs = ["%s%s" % (lib, self.get_lib_suffix()) for lib in self.libs]
        self.cpp_info.defines = ["QT_%s_LIB" % self.module_name.upper()]

        for folder in glob.glob(os.path.join(self.package_folder, "**", "include", "*"), recursive=True):
            self.cpp_info.includedirs.append(folder)

        for folder in glob.glob(os.path.join(self.package_folder, "**", "bin"), recursive=True):
            self.env_info.PATH.append(folder)

        for folder in glob.glob(os.path.join(self.package_folder, "**", "plugins"), recursive=True):
            self.env_info.QT_PLUGIN_PATH.append(folder)

        for folder in glob.glob(os.path.join(self.package_folder, "**", "modules"), recursive=True):
            self.env_info.QMAKEMODULES.append(folder)

        self.env_info.__setattr__("CONAN_PKG_DIR_" + self.name.upper(), self.package_folder)


class QtModuleConan(ConanFile):
    name = "qtmodulepyreq"
    description = "Python base class to be used for Qt module building recipes."
    url = "https://github.com/blixttech/conan-qtmodulepyreq.git"
    homepage = "https://github.com/blixttech/conan-qtmodulepyreq.git"
    license = "LGPL-3.0"  # SPDX Identifiers https://spdx.org/licenses/

    def set_version(self):
        if not self.version:
            git_ref = os.getenv("CONAN_GIT_REF")
            if not git_ref or git_ref == "":
                git = tools.Git(folder=self.recipe_folder)
                git_ref = git.run("describe --all").splitlines()[0].strip()

            self.version = re.sub("^.*/v?|^v?", "", git_ref)
