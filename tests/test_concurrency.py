
import threading
import time
from unittest.mock import patch

def test_restart_tor_service_concurrency():
    from scrapper import restart_tor_service, tor_restart_lock
    import scrapper

    # Reset global state for test
    scrapper.last_tor_restart_time = 0
    
    # Mock subprocess.run to track calls
    with patch('subprocess.run') as mock_run:
        
        def worker():
            restart_tor_service("dummy_command")

        threads = []
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
            
        # Should be called exactly once because of the lock and cooldown
        assert mock_run.call_count == 1
