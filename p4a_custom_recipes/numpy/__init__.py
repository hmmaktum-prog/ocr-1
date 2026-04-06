"""
Custom numpy recipe — fixes broken pypi.python.org download URL.

pypi.python.org legacy URLs (https://pypi.python.org/packages/source/...)
return HTTP 404 since ~2024. This recipe uses the stable GitHub release
archive instead, which is guaranteed to be available.

Also installs setuptools into hostpython3 before building compiled
components, since Python 3.12+ and some hostpython3 builds no longer
ship setuptools by default (numpy 1.x setup.py requires it).
"""

import subprocess
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
        return env

    def prebuild_arch(self, arch):
        """Skip patch application — original patches are iOS-specific, not needed for Android."""
        pass

    def build_compiled_components(self, arch):
        """Ensure setuptools is available in hostpython3 before building numpy extensions."""
        hp = self.hostpython_location

        # Step 1: Try to bootstrap pip into hostpython via ensurepip
        subprocess.run([hp, '-m', 'ensurepip', '--upgrade'], capture_output=True)

        # Step 2: Try installing setuptools using hostpython's pip
        result = subprocess.run(
            [hp, '-m', 'pip', 'install', '--quiet', 'setuptools'],
            capture_output=True
        )

        # Step 3: If hostpython pip still unavailable, use system pip with --target
        if result.returncode != 0:
            try:
                site_dir = subprocess.check_output(
                    [hp, '-c', 'import site; print(site.getsitepackages()[0])'],
                    text=True
                ).strip()
                if site_dir:
                    subprocess.check_call(
                        ['pip3', 'install', '--quiet', '--target', site_dir, 'setuptools']
                    )
            except Exception as e:
                print(f'[numpy recipe] Warning: could not install setuptools: {e}')

        super().build_compiled_components(arch)


recipe = NumpyRecipe()
