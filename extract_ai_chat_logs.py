#!/usr/bin/env python3
"""Extract opencode session chat logs via the opencode CLI.

Default behavior: process ALL sessions run within the current directory
and write one Markdown chat log per session into a ``sessions/``
subdirectory, with filenames keyed by session-start timestamp + session id:

    sessions/YYYYMMDD-HHMMSS_<session-id>.md

Data source: ``opencode session list --format json`` for discovery and
``opencode export <sessionID>`` for the full transcript. No direct
SQLite access (avoids locking the live opencode.db and schema drift).

Stdlib only. Portable on Windows / Linux / macOS.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys


def normalize_dir(path):
    """Canonicalize a directory path for comparison.

    Handles realpath, case-insensitivity on Windows, and / vs \\ slashes.
    """
    p = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    p = os.path.normcase(p)
    p = p.replace("\\", "/").rstrip("/")
    return p


def run_opencode(args, cwd=None):
    """Run `opencode <args>`, return stdout. Raises on failure."""
    try:
        proc = subprocess.run(
            ["opencode"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=cwd,
        )
    except FileNotFoundError:
        raise SystemExit("error: `opencode` binary not found on PATH.")
    if proc.returncode != 0:
        raise RuntimeError(
            "opencode %s failed (exit %d): %s"
            % (" ".join(args), proc.returncode, (proc.stderr or proc.stdout).strip())
        )
    # NOTE: informational lines (e.g. "Exporting session: ...") go to stderr;
    # only stdout carries the JSON payload.
    return proc.stdout


def extract_json_blob(output):
    """Pull the first JSON document ([...] or {...}) out of CLI output.

    Tolerates leading log lines and trailing noise by decoding only the
    first complete JSON document (json.JSONDecoder.raw_decode).
    """
    start_bracket = output.find("[")
    start_brace = output.find("{")
    candidates = [i for i in (start_bracket, start_brace) if i != -1]
    if not candidates:
        raise ValueError("no JSON found in opencode output: %r" % output[:200])
    start = min(candidates)
    doc, _ = json.JSONDecoder().raw_decode(output[start:])
    return doc


def list_sessions(max_count=None, cwd=None):
    # NOTE: `session list` is scoped to the cwd it runs in, so run it from
    # the target directory to discover that directory's sessions.
    args = ["session", "list", "--format", "json"]
    if max_count:
        args += ["-n", str(max_count)]
    return extract_json_blob(run_opencode(args, cwd=cwd))


def export_session(session_id):
    return extract_json_blob(run_opencode(["export", session_id]))


def fmt_time(ms):
    """Format ms-epoch as local 'YYYY-MM-DD HH:MM:SS' plus raw value."""
    if not ms:
        return "unknown"
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return str(ms)


def filename_timestamp(ms):
    """Compact timestamp for filenames: YYYYMMDD-HHMMSS."""
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%Y%m%d-%H%M%S")
    except (OSError, OverflowError, ValueError, TypeError):
        return "unknown-time"


def summarize_tool_input(tool_name, inputs):
    """Pick the most informative input keys for a tool summary."""
    if not isinstance(inputs, dict):
        return ""
    preferred = (
        "command", "filePath", "path", "pattern", "query", "question",
        "prompt", "message", "url", "edits", "content",
    )
    lines = []
    for key in preferred:
        if key in inputs and inputs[key] not in (None, ""):
            val = inputs[key]
            s = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
            if len(s) > 500:
                s = s[:500] + "... [truncated]"
            lines.append("- %s: %s" % (key, s))
    # Include any remaining scalar keys not covered above.
    for key, val in inputs.items():
        if key in preferred:
            continue
        if isinstance(val, (dict, list)):
            continue
        s = str(val)
        if len(s) > 200:
            s = s[:200] + "..."
        lines.append("- %s: %s" % (key, s))
    return "\n".join(lines)


def tool_output_text(state, max_output):
    """Extract human-readable output text from a tool part's state."""
    if not isinstance(state, dict):
        return ""
    for key in ("output", "result", "error"):
        val = state.get(key)
        if isinstance(val, str) and val.strip():
            text = val
            break
        if isinstance(val, dict):
            text = json.dumps(val, indent=2, ensure_ascii=False)
            break
    else:
        metadata = state.get("metadata")
        if isinstance(metadata, dict) and metadata.get("output"):
            text = str(metadata["output"])
        else:
            return ""
    text = text.strip()
    if len(text) > max_output:
        return text[:max_output] + "\n... [truncated %d chars]" % (len(text) - max_output)
    return text


def render_markdown(export_data, max_output, include_reasoning):
    info = export_data.get("info", {})
    messages = export_data.get("messages", [])
    sid = info.get("id", "unknown")
    title = info.get("title", "")
    time_info = info.get("time", {}) if isinstance(info.get("time"), dict) else {}
    created = time_info.get("created")
    updated = time_info.get("updated")
    model = info.get("model", {}) if isinstance(info.get("model"), dict) else {}
    tokens = info.get("tokens", {}) if isinstance(info.get("tokens"), dict) else {}

    lines = []
    lines.append("# %s" % (title or "opencode session"))
    lines.append("")
    lines.append("- session id: `%s`" % sid)
    lines.append("- started: %s (%s)" % (fmt_time(created), created))
    lines.append("- updated: %s (%s)" % (fmt_time(updated), updated))
    lines.append("- directory: `%s`" % info.get("directory", ""))
    agent = info.get("agent", "")
    model_id = model.get("id", "")
    provider = model.get("providerID", "")
    if agent or model_id:
        lines.append("- agent/model: %s / %s (%s)" % (agent, model_id, provider))
    if tokens:
        lines.append(
            "- tokens: input=%s output=%s reasoning=%s cache_read=%s cache_write=%s"
            % (
                tokens.get("input", 0), tokens.get("output", 0),
                tokens.get("reasoning", 0),
                (tokens.get("cache") or {}).get("read", 0),
                (tokens.get("cache") or {}).get("write", 0),
            )
        )
    if info.get("cost") is not None:
        lines.append("- cost: %s" % info.get("cost"))
    lines.append("")
    lines.append("---")
    lines.append("")

    def msg_time(m_info):
        t = m_info.get("time", {}) if isinstance(m_info.get("time"), dict) else {}
        return t.get("created")

    for msg in messages:
        m_info = msg.get("info", {})
        role = m_info.get("role", "unknown")
        mt = fmt_time(msg_time(m_info))
        lines.append("## %s (%s)" % (role.capitalize(), mt))
        lines.append("")
        parts = msg.get("parts", [])
        saw_text = False
        for part in parts:
            ptype = part.get("type", "")
            if ptype == "text":
                text = part.get("text", "")
                if text and text.strip():
                    lines.append(text.strip())
                    lines.append("")
                    saw_text = True
            elif ptype == "reasoning":
                if include_reasoning:
                    text = (part.get("text") or "").strip()
                    if text:
                        lines.append("> Reasoning: %s" % text)
                        lines.append("")
            elif ptype == "tool":
                tool_name = part.get("tool", "tool")
                state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
                status = state.get("status", "")
                lines.append("### Tool `%s`%s" % (tool_name, " (%s)" % status if status else ""))
                lines.append("")
                summary = summarize_tool_input(tool_name, state.get("input", {}))
                if summary:
                    lines.append(summary)
                    lines.append("")
                out = tool_output_text(state, max_output)
                if out:
                    lines.append("```")
                    lines.append(out)
                    lines.append("```")
                    lines.append("")
            elif ptype == "patch":
                # Patch payloads are large; keep a one-line summary.
                lines.append("> File changes applied (patch part `%s`)." % part.get("id", ""))
                lines.append("")
            elif ptype in ("step-start", "step-finish"):
                continue  # internal step markers, skip
            elif ptype == "compaction":
                lines.append("> Context compacted.")
                lines.append("")
            else:
                # Unknown future part type: note it so logs stay lossless-ish.
                lines.append("> [unrendered part type `%s` id `%s`]" % (ptype, part.get("id", "")))
                lines.append("")
        if not saw_text and not parts:
            lines.append("(no parts)")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract opencode session chat logs for a directory into sessions/*.md"
    )
    ap.add_argument("--dir", default=os.getcwd(),
                    help="directory whose sessions to export (default: cwd)")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: <dir>/sessions)")
    ap.add_argument("--session-id", action="append", default=None, dest="session_ids",
                    help="export only this session id (repeatable)")
    ap.add_argument("--max-count", type=int, default=None,
                    help="limit to N most recent sessions (passed to session list)")
    ap.add_argument("--max-output", type=int, default=2000,
                    help="max chars of tool output per tool call (default: 2000)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--overwrite", action="store_true",
                       help="overwrite existing markdown files")
    group.add_argument("--skip-existing", action="store_true",
                       help="skip sessions whose markdown file already exists")
    ap.add_argument("--include-reasoning", action="store_true",
                    help="include reasoning part text in output")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    target = normalize_dir(args.dir)
    out_dir = args.out_dir or os.path.join(os.path.abspath(args.dir), "sessions")
    os.makedirs(out_dir, exist_ok=True)

    try:
        sessions = list_sessions(args.max_count, cwd=os.path.abspath(args.dir))
    except Exception as exc:
        print("error listing sessions: %s" % exc, file=sys.stderr)
        return 1
    if not isinstance(sessions, list):
        print("error: unexpected session list shape", file=sys.stderr)
        return 1

    selected = []
    for s in sessions:
        if args.session_ids and s.get("id") not in args.session_ids:
            continue
        if normalize_dir(s.get("directory", "")) != target:
            continue
        selected.append(s)
    selected.sort(key=lambda s: s.get("created", 0) or 0)

    if not selected:
        print("no sessions found for directory: %s" % os.path.abspath(args.dir))
        return 0

    failures = 0
    written = 0
    skipped = 0
    for s in selected:
        sid = s.get("id", "")
        created = s.get("created")
        fname = "%s_%s.md" % (filename_timestamp(created), sid)
        dest = os.path.join(out_dir, fname)
        if os.path.exists(dest) and not args.overwrite:
            if args.skip_existing or not args.overwrite:
                # Default is skip-with-note unless --overwrite given, so
                # re-runs are idempotent and never clobber edits.
                print("skip (exists): %s" % dest)
                skipped += 1
                continue
        try:
            data = export_session(sid)
        except Exception as exc:
            print("error exporting %s: %s" % (sid, exc), file=sys.stderr)
            failures += 1
            continue
        md = render_markdown(data, args.max_output, args.include_reasoning)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(md)
        print("wrote: %s" % dest)
        written += 1

    print("done: %d written, %d skipped, %d failed (of %d sessions)" % (
        written, skipped, failures, len(selected)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
