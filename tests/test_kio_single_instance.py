from mini_kio.core import single_instance


def test_second_windows_runtime_is_refused(monkeypatch):
    class Kernel32:
        def __init__(self):
            self.closed = []
            def create_mutex(*_args):
                return 42
            def close_handle(handle):
                self.closed.append(handle)
            self.CreateMutexW = create_mutex
            self.CloseHandle = close_handle

    kernel = Kernel32()
    monkeypatch.setattr(single_instance.os, "name", "nt")
    monkeypatch.setattr("ctypes.WinDLL", lambda *_args, **_kwargs: kernel)
    monkeypatch.setattr("ctypes.get_last_error", lambda: 183)
    monkeypatch.setattr(single_instance, "_handle", None)

    assert single_instance.acquire_runtime_owner() is False
    assert kernel.closed == [42]
