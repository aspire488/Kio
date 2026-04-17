import threading
import logging

try:
    import dearpygui.dearpygui as dpg
except ImportError:
    dpg = None

logger = logging.getLogger(__name__)

# States
IDLE = "IDLE"
ACTIVE = "ACTIVE"
LISTENING = "LISTENING"

_current_state = IDLE


def _on_activate_kio(payload) -> None:
    global _current_state
    _current_state = ACTIVE
    print("[UI] KIO activated")
    logger.info("KIO activated via event")


def set_state(state: str) -> None:
    global _current_state
    _current_state = state
    logger.info(f"UI State changed to: {state}")


def _ui_loop() -> None:
    if dpg is None:
        logger.warning("DearPyGui not found. UI skeleton will not render.")
        return

    try:
        dpg.create_context()
        dpg.create_viewport(
            title="Mini-KIO Orb",
            width=200,
            height=200,
            always_on_top=True,
            decorated=False,
            clear_color=[0, 0, 0, 0],
        )

        with dpg.window(
            label="Orb",
            width=200,
            height=200,
            no_title_bar=True,
            no_resize=True,
            no_move=False,
            no_background=True,
        ):
            dpg.add_text("Mini-KIO Floating Orb", color=(0, 255, 0))
            dpg.add_text(f"State: IDLE", tag="state_text", color=(0, 255, 0))

        dpg.setup_dearpygui()
        dpg.show_viewport()

        while dpg.is_dearpygui_running():
            # Update state visually if needed
            dpg.set_value("state_text", f"State: {_current_state}")
            dpg.render_dearpygui_frame()

        dpg.destroy_context()
    except Exception as e:
        logger.error(f"UI Error: {e}")


def start_ui_thread() -> None:
    from .event_bus import subscribe

    subscribe("ACTIVATE_KIO", _on_activate_kio)
    t = threading.Thread(target=_ui_loop, daemon=True, name="kio-ui-thread")
    t.start()
    logger.info("UI thread started.")
