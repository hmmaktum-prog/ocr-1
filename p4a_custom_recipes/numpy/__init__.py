"""
Custom numpy recipe — fixes broken pypi.python.org download URL.

pypi.python.org legacy URLs (https://pypi.python.org/packages/source/...)
return HTTP 404 since ~2024. This recipe uses the stable GitHub release
archive instead, which is guaranteed to be available.

Also installs setuptools into hostpython3 before building compiled
components, since Python 3.12+ and some hostpython3 builds no longer
ship setuptools by default (numpy 1.x setup.py requires it).
"""

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.logger import shprint
import sh


class NumpyRecipe(CompiledComponentsPythonRecipe):
    version = '1.26.4'
    # pypi.python.org is defunct — use GitHub release archive (stable URL)
    url = 'https://github.com/numpy/numpy/archive/refs/tags/v{version}.tar.gz'
    site_packages_name = 'numpy'
    depends = ['cython']

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env['NPY_NUM_BUILD_JOBS'] = '2'
        return env

    def prebuild_arch(self, arch):
        """Skip patch application — original patches are iOS-specific, not needed for Android."""
        pass

    def build_compiled_components(self, arch):
        """Ensure setuptools is available in hostpython3 before building numpy extensions."""
        hp = self.hostpython_location
        shprint(sh.Command(hp), '-m', 'pip', 'install', '--quiet', 'setuptools')
        super().build_compiled_components(arch)


recipe = NumpyRecipe()
