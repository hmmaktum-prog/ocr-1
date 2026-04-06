"""
Custom numpy recipe — fixes broken pypi.python.org download URL.

pypi.python.org legacy URLs (https://pypi.python.org/packages/source/...)
return HTTP 404 since ~2024. This recipe uses the stable GitHub release
archive instead, which is guaranteed to be available.

Also ensures setuptools is importable when numpy's setup.py runs
build_ext with hostpython3 — we inject the system Python's site-packages
via PYTHONPATH so that 'import setuptools' works even though hostpython3
was built without pip/setuptools pre-installed.
"""

import subprocess
import sys
import os
from pythonforandroid.recipe import CompiledComponentsPythonRecipe


class NumpyRecipe(CompiledComponentsPythonRecipe):
    version = '1.26.4'
    # pypi.python.org is defunct — use GitHub release archive (stable URL)
    url = 'https://github.com/numpy/numpy/archive/refs/tags/v{version}.tar.gz'
    site_packages_name = 'numpy'
    depends = ['cython']

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env['NPY_NUM_BUILD_JOBS'] = '2'

        # Inject the system Python's site-packages into PYTHONPATH so that
        # numpy's setup.py can 'import setuptools' when build_ext runs via
        # hostpython3 (which has no setuptools of its own).
        try:
            sys_site = subprocess.check_output(
                [sys.executable, '-c',
                 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                text=True
            ).strip()
            if sys_site and os.path.isdir(sys_site):
                existing = env.get('PYTHONPATH', '')
                env['PYTHONPATH'] = (
                    sys_site + (':' + existing if existing else '')
                )
        except Exception as e:
            print(f'[numpy recipe] Warning: could not set PYTHONPATH: {e}')

        return env

    def prebuild_arch(self, arch):
        """Skip patch application — original patches are iOS-specific."""
        pass


recipe = NumpyRecipe()
