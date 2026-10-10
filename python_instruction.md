tanding conventions for this script. The actual task/functionality is specified separately — implement these conventions together with that task.

General

-Before generating code, if there are unclarities, do ask, do not guess.

-Prefer the standard library; if a third-party package is genuinely needed, name it explicitly and note it in a comment at the top.

-Use argparse for command-line handling.

-Initialize argparse in a dedicated subroutine.

-Use exit code 0 for success, non-zero for errors, consistently throughout.

 

Input/output

 

- Read input from stdin by default, unless -f/--file is given, in which case read from that file instead.

- For the -f file path: auto-detect encoding (don't assume UTF-8) — Windows/Excel-originated files are often cp1252 and can contain bytes that break strict UTF-8 decoding.

- For stdin: assume UTF-8 (or reconfigure stdin to UTF-8 explicitly), since encoding auto-detection only applies to the -f file path.

- Explicitly set encoding='utf-8' on any file or stream the script writes — including the log file (pass encoding='utf-8' to logging.FileHandler explicitly; it doesn't inherit this automatically) — since Windows defaults to the system codepage, which can crash on non-ASCII output.

- Wrap sys.stdout/sys.stderr for UTF-8 output if the script prints non-ASCII characters, since Windows consoles often aren't UTF-8 by default.

- Always open text files with newline='' when using the csv module, and don't assume \n vs \r\n line endings.

 

Logging

 

- If -d is given, log at DEBUG level to a file named <script_stem>.log placed next to the script (same directory), where <script_stem> is the script's filename without extension. Console output (stdout/stderr) is unaffected by -d.

- Define the log filename as a module-level constant near the top of the script.

 

Cross-platform (must run identically on Linux and Windows)

 

- Use pathlib.Path for all file paths instead of manual string concatenation or hardcoded / or \.

- Avoid OS-specific calls (os.system, shell-specific commands, POSIX-only modules) — stick to standard-library cross-platform APIs.

- Don't rely on case-sensitive filesystem behavior, since Windows is case-insensitive by default.ently across the script.

