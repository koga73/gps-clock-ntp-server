import micropython
import time
import _thread
from machine import Pin
from array import array

from lib.l76x import L76X

class GPS():
    # Constructor
    def __init__(self, pps_pin = 16):
        self._lock = _thread.allocate_lock()

        self._pps = None
        self._pps_pin = pps_pin

        # Preallocate memory for hard irq
        self._irq_pps = array("i", [0, 1000000]) # [pps_last_tick, pps_ticks_per_second]

    def init(self):
        gps = L76X()
        gps.L76X_Set_Baudrate(9600)
        time.sleep_ms(1000)

        # Increase BAUD rate for faster NMEA parsing
        gps.L76X_Send_Command(gps.SET_NMEA_BAUDRATE_115200)
        time.sleep_ms(1000)
        gps.L76X_Set_Baudrate(115200)

        # Timing
        gps.L76X_Send_Command(gps.SET_POS_FIX_1S)
        gps.L76X_Send_Command(gps.SET_PPS_ON)

        # Output format
        gps.L76X_Send_Command(gps.SET_NMEA_OUTPUT)
        gps.L76X_Exit_BackupMode()

        self.gps = gps

        # Allocate exception buffer for IRQ handler
        micropython.alloc_emergency_exception_buf(128)

        pps = Pin(self._pps_pin, Pin.IN)
        pps.irq(trigger = Pin.IRQ_RISING, handler = self._handle_pps, hard = True)
        self._pps = pps

    # PPS signal IRQ handler, capture the tick and compute the ticks-per-second
    def _handle_pps(self, _pin):
        pps_tick = time.ticks_us()

        irq_pps = self._irq_pps
        
        delta = time.ticks_diff(pps_tick, irq_pps[0])
        irq_pps[0] = pps_tick
        
        # Ignore if the delta is too far off
        if (950000 < delta < 1050000):
            irq_pps[1] = delta

    # Call from main loop
    def loop(self):
        return self.gps.L76X_Receive()

    # Return tuple of (last_pps_tick, ticks_per_second)
    def get_pps(self):
        with self._lock:
            irq_pps = self._irq_pps
            return irq_pps[0], irq_pps[1]

    def get_satellites(self):
        with self._lock:
            return self.gps.Satellites

    def get_datetime(self):
        with self._lock:
            gps = self.gps
            year, month, day = gps.Time_Year, gps.Time_Month, gps.Time_Day
            hours, minutes, seconds = gps.Time_Hours, gps.Time_Minutes, gps.Time_Seconds
            microseconds = gps.Time_Microseconds
        
        weekday = 0 # Not supported by GPS
        return (
            year, month, day,
            weekday,
            hours, minutes, seconds,
            microseconds
        )

    def get_timestamp(self):
        with self._lock:
            return self.gps.Timestamp

    def get_lat(self):
        with self._lock:
            return self.gps.Lat

    def get_lon(self):
        with self._lock:
            return self.gps.Lon
    
    def get_altitude(self):
        with self._lock:
            return self.gps.Altitude

    def get_height(self):
        with self._lock:
            return self.gps.Height

    def has_fix(self):
        with self._lock:
            return self.gps.Satellites > 0
