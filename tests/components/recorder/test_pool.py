"""Test pool."""
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from homeassistant.components.recorder.const import DB_WORKER_PREFIX
from homeassistant.components.recorder.pool import RecorderPool


def test_recorder_pool(caplog):
    """Test RecorderPool gives the same connection in the creating thread."""

    engine = create_engine("sqlite://", poolclass=RecorderPool)
    get_session = sessionmaker(bind=engine)
    shutdown = False
    connections = []

    def _get_connection_twice():
        session = get_session()
        connections.append(session.connection().connection.connection)
        session.close()

        if shutdown:
            engine.pool.shutdown()

        session = get_session()
        connections.append(session.connection().connection.connection)
        session.close()

    _get_connection_twice()
    assert "accesses the database without the database executor" in caplog.text
    assert connections[0] != connections[1]

    caplog.clear()
    new_thread = threading.Thread(target=_get_connection_twice)
    new_thread.start()
    new_thread.join()
    assert "accesses the database without the database executor" in caplog.text
    assert connections[2] != connections[3]

    caplog.clear()
    new_thread = threading.Thread(target=_get_connection_twice, name=DB_WORKER_PREFIX)
    new_thread.start()
    new_thread.join()
    assert "accesses the database without the database executor" not in caplog.text
    assert connections[4] == connections[5]

    caplog.clear()
    new_thread = threading.Thread(target=_get_connection_twice, name="Recorder")
    new_thread.start()
    new_thread.join()
    assert "accesses the database without the database executor" not in caplog.text
    assert connections[6] == connections[7]

    shutdown = True
    caplog.clear()
    new_thread = threading.Thread(target=_get_connection_twice, name=DB_WORKER_PREFIX)
    new_thread.start()
    new_thread.join()
    assert "accesses the database without the database executor" not in caplog.text
    assert connections[8] != connections[9]
