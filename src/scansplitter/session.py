"""Session management for temporary file storage."""

import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_name(value: str | None, default: str = "file", allow_dot: bool = True) -> str:
    """Sanitize a client-supplied string into a safe single path component.

    Drops any directory portion, strips null bytes, replaces disallowed
    characters with ``_`` and rejects empty / dot-only results (``.``, ``..``),
    returning ``default`` in that case. The result never contains a path
    separator, so it is safe to join onto a trusted base directory.

    Args:
        value: The untrusted name to sanitize.
        default: Fallback returned when the sanitized result is unusable.
        allow_dot: When ``False`` dots are also stripped (used for identifiers).
    """
    if not value:
        return default

    # Keep only the final path component and never treat backslashes as dirs.
    candidate = value.replace("\x00", "").replace("\\", "/")
    candidate = candidate.rsplit("/", 1)[-1]

    pattern = _SAFE_NAME_RE if allow_dot else _SAFE_ID_RE
    candidate = pattern.sub("_", candidate).strip()

    # Reject empty results or names consisting solely of dots ('.', '..').
    if not candidate or set(candidate) <= {"."}:
        return default

    return candidate


@dataclass
class Session:
    """A user session with uploaded files and state."""

    id: str
    created_at: float
    directory: Path
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    cropped_images: list[Path] = field(default_factory=list)
    exif_data: dict[str, dict[str, Any]] = field(default_factory=dict)  # filename -> exif
    last_accessed: float = 0.0
    # Small cache of rendered PDF pages: (filename, page) -> PIL Image
    page_cache: dict[tuple[str, int], Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.last_accessed:
            self.last_accessed = self.created_at

    def touch(self) -> None:
        """Mark the session as recently used (resets idle-based cleanup)."""
        self.last_accessed = time.time()

    @property
    def age_seconds(self) -> float:
        """Return session age in seconds."""
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Return seconds since the session was last accessed."""
        return time.time() - self.last_accessed


class SessionManager:
    """Manages temporary sessions for file uploads and processing."""

    def __init__(
        self,
        base_dir: Path | None = None,
        max_age_seconds: float = 3600,  # 1 hour
        cleanup_interval: float = 300,  # 5 minutes
    ):
        """
        Initialize session manager.

        Args:
            base_dir: Base directory for session storage. Uses temp dir if None.
            max_age_seconds: Maximum session age before cleanup.
            cleanup_interval: How often to run cleanup (seconds).
        """
        if base_dir is None:
            import tempfile

            base_dir = Path(tempfile.gettempdir()) / "scansplitter_sessions"

        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.max_age_seconds = max_age_seconds
        self.cleanup_interval = cleanup_interval
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def create_session(self) -> Session:
        """Create a new session with unique ID."""
        # Full 128-bit UUID: session IDs are the only access control, so
        # keep full entropy (a truncated ID would be guessable when the
        # server is exposed beyond localhost).
        session_id = uuid.uuid4().hex
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        session = Session(
            id=session_id,
            created_at=time.time(),
            directory=session_dir,
        )

        with self._lock:
            self._sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID and mark it as recently used."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its files."""
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None:
            return False

        # Imported lazily to avoid coupling session creation to the job executor.
        from .jobs import registry

        registry.drop_session(session_id)

        # Remove directory
        if session.directory.exists():
            shutil.rmtree(session.directory, ignore_errors=True)

        return True

    def cleanup_old_sessions(self) -> int:
        """Remove sessions idle for longer than max_age_seconds.

        Uses last-accessed time (not creation time) so an actively used
        session is never deleted out from under the user.
        """
        now = time.time()
        to_delete = []

        with self._lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed > self.max_age_seconds:
                    to_delete.append(session_id)

        deleted = 0
        for session_id in to_delete:
            if self.delete_session(session_id):
                deleted += 1

        return deleted

    def _cleanup_loop(self):
        """Background cleanup loop."""
        while True:
            time.sleep(self.cleanup_interval)
            try:
                self.cleanup_old_sessions()
            except Exception:
                pass  # Ignore errors in cleanup


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
