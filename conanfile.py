from conans import ConanFile, CMake, tools, VisualStudioBuildEnvironment
from conans.tools import cpu_count, os_info, SystemPackageTool
from conans.errors import ConanException
from distutils.spawn import find_executable
import os, re, glob, pathlib

class QtModuleConanBase(object):

    def set_version(self):
        git = tools.Git(folder=self.recipe_folder)
        version = re.sub(".*/", "", str(git.get_branch()))
        self.version = version

    def requirements(self):
        self.requires("qt/%s@bincrafters/stable" % self.version)

    def source(self):
        source_folder = os.path.join(self.source_folder, self.name)
        git = tools.Git(folder=source_folder)
        git.clone(("https://code.qt.io/qt/%s.git" % self.name), "v" + self.version)

    def build(self):
        if self.settings.os == "Windows" and (not self.settings.compiler == "Visual Studio"):
            raise ConanException("Not yet implemented for this compiler")

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
        if not self.options.shared:
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
            with tools.environment_append(env_build.vars):
                vcvars_cmd = tools.vcvars_command(self.settings)
                self.run("%s && %s %s" % (vcvars_cmd, qmake_command, " ".join(qmake_args)),
                        cwd=build_folder)
                self.run("%s && %s %s" % (vcvars_cmd, build_command, " ".join(build_args)),
                        cwd=build_folder)
        else:
            self.run("%s %s" % (qmake_command, " ".join(qmake_args)), cwd=build_folder)
            self.run("%s %s" % (build_command, " ".join(build_args)), cwd=build_folder)

    def package(self):
        build_folder = os.path.join(self.build_folder, ("%s-build" % self.name))
        install_folder = os.path.join(self.build_folder, ("%s-install" % self.name))
        # Try to find the location where the files are installed.
        folders = glob.glob(os.path.join(install_folder, "**", ".conan", "**", "mkspecs"), 
                                        recursive=True)
        if len(folders) == 0:
            raise ConanException("Cannot find installation directory")

        install_prefix = pathlib.Path(folders[0]).parent

        self.copy("*", dst="bin", src=os.path.join(install_prefix, "bin"), symlinks=True)
        self.copy("*", dst="include", src=os.path.join(install_prefix, "include"), symlinks=True)
        self.copy("*", dst="lib", src=os.path.join(install_prefix, "lib"), symlinks=True)
        # We use forwarding .pri files instead of using direct .pri files.
        self.copy("*", dst="mkspecs", src=os.path.join(build_folder, "mkspecs"), symlinks=True)
        self.copy("*", dst="plugins", src=os.path.join(install_prefix, "plugins"), symlinks=True)
        
        # qmake loads Qt modules in <Qt SDK Dir>/mkspecs/features/qt_config.prf file.
        # In this file, QMAKEMODULES environmental variable is searched for additional module directories.
        # As we build modules seperately, we have to adjust the correct path dynamically in the
        # forwarding .pri files.
        # So, we use an uniq environmental variable for each module to specify the package path.
        for filename in glob.iglob(os.path.join(self.package_folder, 
                                                "mkspecs", "modules", "**", "*.pri"), 
                                    recursive=True):
            tools.replace_path_in_file(filename, 
                                        build_folder, 
                                        "$$(CONAN_PKG_DIR_" + self.name.upper() + ")", 
                                        strict=False)

    def package_info(self):
        if os.path.exists(os.path.join(self.package_folder, "bin")):
            self.env_info.PATH.append(os.path.join(self.package_folder, "bin"))
        if os.path.exists(os.path.join(self.package_folder, "plugins")):
            self.env_info.QT_PLUGIN_PATH.append(os.path.join(self.package_folder, "plugins"))

        self.env_info.CMAKE_PREFIX_PATH.append(self.package_folder) 
        self.env_info.QMAKEMODULES.append(os.path.join(self.package_folder, "mkspecs", "modules"))
        self.env_info.__setattr__("CONAN_PKG_DIR_" + self.name.upper(), self.package_folder)


class QtModuleConan(ConanFile):
    name = "qtmodulepyreq"

    def set_version(self):
        git = tools.Git(folder=self.recipe_folder)
        version = re.sub(".*/", "", str(git.get_branch()))
        self.version = version