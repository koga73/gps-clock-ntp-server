import micropython
import asyncio
import time
import _thread
import machine
from machine import Pin
from array import array

from lib.l76x import L76X

class GPS():
    _satellites = 0
    _lat = None
    _lon = None
    _altitude = 0.0
    _height = 0.0
    _timestamp = ""
    _datetime = None

    def __init__(self, pps_pin = 16):
        self._lock = _thread.allocate_lock()

        self._gps = L76X()

        # Preallocate memory for hard irq
        self._irq_pps = array("i", [0, 1000000]) # [pps_last_tick, pps_ticks_per_second]
        self._pps = Pin(pps_pin, Pin.IN)

    def init(self):
        gps = self._gps

        # Satellites
        # gps.L76X_Send_Command(gps.SET_SATELLITES_GPS_BEIDOU)
        # gps.L76X_Send_Command(gps.SET_RESTART_WARM)
        
        # Increase BAUD rate for faster NMEA parsing
        time.sleep_ms(1000)
        gps.L76X_Send_Command(gps.SET_BAUDRATE_115200)
        time.sleep_ms(1000)
        gps.L76X_Set_Baudrate(115200)

        # Timing
        gps.L76X_Send_Command(gps.SET_FREQUENCY_1S)
        # Output format
        gps.L76X_Send_Command(gps.SET_NMEA_OUTPUT)
        # Exit backup
        gps.L76X_Exit_BackupMode()

        # Allocate exception buffer for IRQ handler
        micropython.alloc_emergency_exception_buf(128)
        self._pps.irq(trigger = Pin.IRQ_RISING, handler = self._handle_pps, hard = True)

    # PPS signal IRQ handler, capture the tick and compute the ticks-per-second
    def _handle_pps(self, _pin):
        pps_tick = time.ticks_us()

        irq_pps = self._irq_pps
        
        delta = time.ticks_diff(pps_tick, irq_pps[0])
        irq_pps[0] = pps_tick
        
        # Ignore if the delta is too far off
        if (950000 < delta < 1050000):
            irq_pps[1] = delta

    # Return tuple of (last_pps_tick, ticks_per_second)
    def get_pps(self):
        state = machine.disable_irq()
        try:
            irq_pps = self._irq_pps
            return irq_pps[0], irq_pps[1]
        finally:
            machine.enable_irq(state)

    # Call from main loop
    def loop(self):
        did_change_time = self._gps.L76X_Receive()

        with self._lock:
            gps = self._gps
            
            satellites = gps.satellites
            self._satellites = satellites

            if (satellites > 0):
                self._lat = gps.lat
                self._lon = gps.lon
                self._altitude = gps.altitude
                self._height = gps.height
            
            if (did_change_time):
                self._timestamp = gps.timestamp
                self._datetime = (
                    gps.time_year, gps.time_month, gps.time_day,
                    0, # Weekday not supported by GPS
                    gps.time_hours, gps.time_minutes, gps.time_seconds,
                    gps.time_microseconds
                )

        return did_change_time
    
    def get_satellites(self):
        with self._lock:
            return self._satellites
    
    def get_lat(self):
        with self._lock:
            return self._lat

    def get_lon(self):
        with self._lock:
            return self._lon
    
    def get_altitude(self):
        with self._lock:
            return self._altitude

    def get_height(self):
        with self._lock:
            return self._height

    def get_timestamp(self):
        with self._lock:
            return self._timestamp
    
    def get_datetime(self):
        with self._lock:
            return self._datetime

    def has_fix(self):
        with self._lock:
            return self._satellites > 0

    def factory_reset(self):
        self._gps.L76X_Send_Command(self._gps.SET_RESTART_RESET)
        time.sleep_ms(1000)
