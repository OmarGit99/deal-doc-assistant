from app.compat import use_selector_event_loop_on_windows

# The database tests use async psycopg, which needs this on Windows.
use_selector_event_loop_on_windows()
