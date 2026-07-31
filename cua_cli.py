import sys, pathlib, importlib.util

# Add the external CUA CLI package directory to sys.path
EXTERNAL_PATH = pathlib.Path(__file__).resolve().parents[0] / "external" / "cua" / "libs" / "python" / "cua-cli"
if str(EXTERNAL_PATH) not in sys.path:
    sys.path.append(str(EXTERNAL_PATH))
# Load the real main module from the external package
real_main_path = EXTERNAL_PATH / "cua_cli" / "main.py"
spec = importlib.util.spec_from_file_location("_cua_cli_main", real_main_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__ == "__main__":
    sys.exit(module.main())
