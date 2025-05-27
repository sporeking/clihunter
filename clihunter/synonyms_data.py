import re
from typing import List, Dict

SYNONYM_GROUPS = [
    # --- useful similiar command ---
    ["add", "new", "create", "make", "mk", "generate", "insert", "append"],
    ["remove", "delete", "erase", "rm", "del", "unset", "discard", "drop"],
    ["find", "search", "locate", "look for", "query", "seek", "grep", "filter"], 
    ["show", "display", "list", "view", "print", "cat", "echo", "ls", "output", "get", "retrieve", "fetch"], 
    ["edit", "modify", "change", "update", "set", "alter", "revise"],
    ["copy", "cp", "duplicate", "clone"],
    ["move", "mv", "rename", "relocate"],
    ["run", "execute", "exec", "start", "launch", "invoke", "initiate"],
    ["stop", "kill", "terminate", "halt", "end", "cancel"],
    ["install", "setup", "deploy", "get"],
    ["uninstall", "remove software", "purge"],
    ["update", "upgrade", "patch", "refresh", "sync", "synchronize"],
    ["ssh", "login", "access"], 
    ["disconnect", "logout", "exit"],
    ["download", "fetch", "get", "pull"],
    ["upload", "push", "send", "put"],
    ["compress", "zip", "archive", "tar", "gzip", "bzip2", "pack"], 
    ["decompress", "unzip", "untar", "extract", "unpack"],
    ["mount", "attach"],
    ["unmount", "detach", "eject"],
    ["check", "verify", "validate", "test", "inspect"],
    ["compare", "diff", "contrast"],
    ["merge", "combine", "join"],
    ["split", "divide", "separate"],
    ["backup", "save", "dump"],
    ["restore", "recover", "load"],
    ["monitor", "watch", "observe", "track"],
    ["clear", "clean", "reset"],
    ["convert", "transform", "change format"],

    # --- Highly specific terms ---
    ["file", "files", "document", "documents", "item", "object"],
    ["directory", "dir", "folder", "path", "location"],
    ["config", "configuration", "settings", "preferences", "prefs", "conf", "params", "parameters"],
    ["process", "processes", "task", "tasks", "proc", "job", "service", "daemon"],
    ["log", "logs", "history", "journal", "audit", "event", "events"],
    ["network", "net", "connection", "lan", "wan"],
    ["user", "users", "account", "accounts", "profile"],
    ["permission", "permissions", "rights", "access control", "acl", "chmod", "chown"], 
    ["package", "packages", "software", "app", "application", "program", "tool", "utility"],
    ["script", "scripts", "automation", "batch"],
    ["key", "keys", "ssh-key", "gpg-key", "secret", "password", "credential"],
    ["large", "big", "huge", "massive", "size"],
    ["small", "tiny", "little", "mini"],
    ["all", "every", "everything", "complete", "entire"],
    ["active", "running", "enabled", "current", "live"],
    ["inactive", "stopped", "disabled"],
    ["remote", "server", "host", "cloud"],
    ["local", "localhost", "desktop", "workstation"],
    ["text", "string", "content", "pattern"],
    ["image", "picture", "photo", "img"],
    ["video", "movie", "clip", "vid"],
    ["audio", "sound", "music", "snd"],
    ["port", "ports", "socket"],
    ["version", "release", "ver"],
    ["system", "sys", "os", "operating system", "machine", "host"],
    ["disk", "storage", "drive", "partition", "space", "hdd", "ssd"],
    ["memory", "mem", "ram"],
    ["cpu", "processor"],
    ["date", "time", "timestamp", "when"],
    ["error", "errors", "issue", "problem", "bug", "failure", "exception"],
    ["status", "state", "info", "information", "details"],
    ["output", "result", "response"],
    ["input", "argument", "parameter"],
    ["temporary", "temp", "tmp"],
    ["default", "standard", "normal"],
    ["interface", "adapter", "nic"], # Network Interface Card

    # --- Usual command ---
    ["ls", "list files", "list directory"], 
    ["cd", "change directory"],
    ["pwd", "print working directory", "current path"],
    ["grep", "search text", "find in files", "filter content"],
    ["find", "find files", "search files by name"], 
    ["awk", "text processing", "column processing"],
    ["sed", "stream editor", "text manipulation"],
    ["tar", "tape archive", "archiver"],
    ["zip", "zipper", "compress files"],
    ["git", "version control", "source control", "repo", "repository"],
    ["docker", "container", "containers", "virtualization"],
    ["ssh", "secure shell", "remote login", "remote access"],
    ["scp", "secure copy", "remote copy"],
    ["rsync", "remote sync", "file synchronization"],
    ["curl", "client url", "http request", "download url"],
    ["wget", "web get", "download file"],
    ["ping", "network test", "check host"],
    ["netstat", "network statistics", "listening ports"],
    ["ss", "socket statistics", "show connections"], 
    ["top", "processes usage", "system monitor"],
    ["htop", "interactive top"],
    ["ps", "process status", "list processes"],
    ["kill", "terminate process"],
    ["df", "disk free", "filesystem space"],
    ["du", "disk usage", "file size"],
    ["chmod", "change mode", "set permissions"],
    ["chown", "change owner"],
    ["sudo", "superuser do", "run as root", "elevate privilege"],
    ["apt", "apt-get", "debian package manager", "ubuntu package manager"],
    ["yum", "centos package manager", "redhat package manager", "dnf"],
    ["brew", "homebrew", "macos package manager"],
    ["make", "compile", "build"], 
    ["vim", "vi", "text editor"],
    ["nano", "text editor"],
    ["code", "vscode", "visual studio code"],
    ["python", "py"],
    ["node", "nodejs", "javascript runtime"],
    ["java", "jdk"],
    ["systemctl", "systemd control", "manage services"],
    ["journalctl", "journal control", "view logs"],

    ["variable", "var", "env var"],
    ["function", "func", "method", "subroutine"],
    ["loop", "for loop", "while loop", "iterate"],
    ["conditional", "if statement", "if else"],
    ["array", "list", "sequence"], 
    ["object", "dictionary", "map", "hash", "struct"], 
    ["string", "text"],
    ["integer", "int", "number"],
    ["float", "double", "decimal"],
    ["boolean", "bool", "true", "false"],
    ["null", "none", "nil", "empty"],
    ["debug", "troubleshoot", "diagnose"],
    ["test", "testing", "unit test", "integration test"],
]

_SYNONYM_LOOKUP_MAP = None # 保持这个查找map的逻辑不变

def get_synonym_lookup_map() -> Dict[str, List[str]]:
    """
    Convert SYNONYM_GROUPS into a lookup dictionary for fast retrieval of synonyms (including itself).
    Key is each term in the group, and value is the complete synonym group it belongs to.
    """
    global _SYNONYM_LOOKUP_MAP
    if _SYNONYM_LOOKUP_MAP is None:
        _SYNONYM_LOOKUP_MAP = {}
        for group in SYNONYM_GROUPS:
            normalized_group = sorted(list(set(term.lower() for term in group)))
            for term in normalized_group:
                _SYNONYM_LOOKUP_MAP[term] = normalized_group
    return _SYNONYM_LOOKUP_MAP

if __name__ == "__main__":
    s_map = get_synonym_lookup_map()
    # Test the lookup map
    print(f"Synonyms for 'find': {s_map.get('find')}")
    print(f"Synonyms for 'grep': {s_map.get('grep')}")
    print(f"Synonyms for 'nonexistent': {s_map.get('nonexistent')}")
    print(f"Total unique terms: {len(s_map)}")