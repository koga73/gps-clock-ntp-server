# https://github.com/waveshare/L76X-GPS-Module/blob/master/python/L76X.py

from machine import Pin
import time

from l76_config import L76_Config 
import micropyGPS as Parser

Temp = '0123456789ABCDEF*'

class L76X(object):
    # Baud rate
    SET_BAUDRATE          = '$PCAS01'
    SET_BAUDRATE_115200   = '$PCAS01,5'
    SET_BAUDRATE_57600    = '$PCAS01,4'
    SET_BAUDRATE_38400    = '$PCAS01,3'
    SET_BAUDRATE_19200    = '$PCAS01,2'
    SET_BAUDRATE_9600     = '$PCAS01,1'
    SET_BAUDRATE_4800     = '$PCAS01,0'

    # Set the message frequency
    SET_FREQUENCY         = '$PCAS02'
    SET_FREQUENCY_200MS   = '$PCAS02,200'
    SET_FREQUENCY_500MS   = '$PCAS02,500'
    SET_FREQUENCY_1S      = '$PCAS02,1000'

    # Set NMEA sentence output 
    # GGA, GLL, GSA, GSV, RMC, VTG, ZDA, ANT
    SET_NMEA_OUTPUT = '$PCAS03,1,1,1,1,1,1,1,1,0,0,,,0,0'

    # Set satellite system
    SET_SATELLITES = "$PCAS04"
    SET_SATELLITES_GPS = "$PCAS04,1"
    SET_SATELLITES_BEIDOU = "$PCAS04,2"
    SET_SATELLITES_GPS_BEIDOU = "$PCAS04,3" # Default
    SET_SATELLITES_GLONASS = "$PCAS04,4"
    SET_SATELLITES_GPS_GLONASS = "$PCAS04,5"
    SET_SATELLITES_BEIDOU_GLONASS = "$PCAS04,6"
    SET_SATELLITES_GPS_BEIDOU_GLONASS = "$PCAS04,7"

    # Set restart mode
    SET_RESTART = "$PCAS10"
    SET_RESTART_HOT = "$PCAS10,0"
    SET_RESTART_WARM = "$PCAS10,1"
    SET_RESTART_COLD = "$PCAS10,2"
    SET_RESTART_RESET = "$PCAS10,3" # Factory reset

    satellites = 0
    lon = 0.0
    lat = 0.0
    altitude = 0.0
    height = 0.0

    time_year = 0
    time_month = 0
    time_day = 0
    time_hours = 0
    time_minutes = 0
    time_seconds = 0
    time_microseconds = 0
    timestamp = "" # "0000-00-00 00:00:00.0" # Unix format

    def __init__(self):
        self.config = L76_Config(9600)

        # location_formatting (str): Style For Presenting Longitude/Latitude:
        # Decimal Degree Minute (ddm) - 40° 26.767′ N
        # Degrees Minutes Seconds (dms) - 40° 26′ 46″ N
        # Decimal Degrees (dd) - 40.446° N
        self.parser = Parser.MicropyGPS()
    
    def L76X_Send_Command(self, data):
        Check = ord(data[1]) 
        for i in range(2, len(data)):
            Check = Check ^ ord(data[i])
        data = data + Temp[16]
        data = data + Temp[int(Check/16)]
        data = data + Temp[int(Check%16)]

        self.config.Uart_SendString(data)
        self.config.Uart_SendByte('\r')
        self.config.Uart_SendByte('\n')
        # print(data)

    # Clear the GPS UART buffer
    def L76X_Flush(self):
        raw_data = self.config.Uart_ReceiveAll()

        if (len(raw_data) == 0):
            return False
        
        for b in raw_data:
            try: self.parser.update(chr(b))
            except: continue
    
    # Read from GPS UART, parse and update time
    def L76X_Receive(self):
        self.L76X_Flush()

        # Update satellites
        self.satellites = self.parser.satellites_in_use

        # Ensure we have a satellite fix
        if (self.satellites == 0):
            return False
        
        # Update coordinates
        self.lat = self.parser.latitude
        self.lon = self.parser.longitude
        self.altitude = self.parser.altitude
        self.height = self.parser.geoid_height
        
        # Update time
        day, month, year = self.parser.date
        hours, minutes, seconds_raw = self.parser.timestamp

        # Ensure we have date
        if (year == 0 or month == 0 or day == 0):
            return False

        seconds = int(seconds_raw)
        microseconds = int(round((seconds_raw - seconds) * 1000000))
        if microseconds >= 1000000:
            microseconds = 0
            seconds += 1
        
        # Ensure has changed
        if (
            year + 2000, month, day,
            hours, minutes, seconds,
            microseconds
        ) == (
            self.time_year, self.time_month, self.time_day,
            self.time_hours, self.time_minutes, self.time_seconds,
            self.time_microseconds
        ): return False
        
        self.time_year = year + 2000 # GPS returns year as 2 digit format
        self.time_month = month
        self.time_day = day
        self.time_hours = hours
        self.time_minutes = minutes
        self.time_seconds = seconds
        self.time_microseconds = microseconds
        self.timestamp = self._create_timestamp_str(year, month, day, hours, minutes, seconds, microseconds)

        return True
    
    def _create_timestamp_str(self, year, month, day, hours, minutes, seconds, microseconds = 0):
        # Pad with leading zero if needed
        year = "20{:02d}".format(year)
        month = "{:02d}".format(month)
        day = "{:02d}".format(day)
        hours = "{:02d}".format(hours)
        minutes = "{:02d}".format(minutes)
        seconds = "{:02d}".format(seconds)
        microseconds = "{:06d}".format(microseconds)

        return f"{year}-{month}-{day} {hours}:{minutes}:{seconds}.{microseconds}"

    def L76X_Set_Baudrate(self, Baudrate):
        self.config.Uart_Set_Baudrate(Baudrate)

    def L76X_Exit_BackupMode(self):
        self.config.Force.value(1)
        time.sleep(1)
        self.config.Force.value(0)
        time.sleep(1)
        self.config.Force = Pin(self.config.force_pin, Pin.IN)
