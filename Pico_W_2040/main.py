# main.py -- BLE + MPU6050 data streaming 

import aioble
import asyncio
import bluetooth
from machine import Pin, PWM, I2C, ADC
import struct
from libs.imu import MPU6050
import time
import ujson
import math
from libs.vl53l0x import VL53L0X

def read_scaled(self):
    x, y, z = self.read()
    scale = 0.00073  # QMC5883L 2G range LSB → gauss
    return x*scale, y*scale, z*scale

def safe_asin(value):
    """Clamp value for math.asin to avoid domain errors."""
    if value > 1: value = 1
    if value < -1: value = -1
    return math.asin(value)

def get_heading(x, y):
    heading = math.atan2(y, x)
    heading_deg = heading * 180 / math.pi

    if heading_deg < 0:
        heading_deg += 360

    return heading_deg

def compute_offsets(min_v, max_v):
    return (max_v + min_v) / 2

def compute_scale(min_v, max_v):
    return (max_v - min_v) / 2

def compute_accel_offsets(min_v, max_v, g_axis=False):
    """
    Compute accelerometer offset.
    If g_axis=True, subtract gravity so level Z reads 0.
    """
    offset = (max_v + min_v) / 2
    if g_axis:
        offset -= 16384  # adjust for 1g (replace 16384 with your sensor units for 1g)
    return offset

def get_cardinal_direction(heading_deg):
    try:
        if (heading_deg >= 315 or heading_deg < 45):
            return "N"
        elif (heading_deg >= 45 and heading_deg < 135):
            return "E"
        elif (heading_deg >= 135 and heading_deg < 225):
            return "S"
        else:
            return "W"
    except:
        return "N"
    
def tilt_compensated_heading(mx, my, mz, pitch, roll):
    try:
        # Convert degrees → radians
        pitch = math.radians(pitch)
        roll  = math.radians(roll)

        # Tilt compensation
        Xh = mx * math.cos(pitch) + mz * math.sin(pitch)
        Yh = (mx * math.sin(roll) * math.sin(pitch) +
              my * math.cos(roll) -
              mz * math.sin(roll) * math.cos(pitch))

        heading = math.atan2(Yh, Xh)
        heading_deg = math.degrees(heading)

        if heading_deg < 0:
            heading_deg += 360

        return heading_deg

    except Exception as e:
        print("Heading calc error:", e)
        return 0
    


def update_gy271_calibration(self, mx, my, mz):
    """Call this each loop iteration while calibrating."""
    if not getattr(self, "calibrating", False):
        return

    # Update min/max values
    self.min_x = min(self.min_x, mx)
    self.max_x = max(self.max_x, mx)
    self.min_y = min(self.min_y, my)
    self.max_y = max(self.max_y, my)
    self.min_z = min(self.min_z, mz)
    self.max_z = max(self.max_z, mz)

    # Compute offsets
    self.offset_x = compute_offsets(self.min_x, self.max_x)
    self.offset_y = compute_offsets(self.min_y, self.max_y)
    self.offset_z = compute_offsets(self.min_z, self.max_z)

    # Optional: stop calibration after 20 seconds
    if time.time() - getattr(self, "calibration_start_time", 0) > 20:
        self.calibrating = False
        print("Calibration complete!")
        print(f"Offsets: X={self.offset_x}, Y={self.offset_y}, Z={self.offset_z}")

def fuse_heading(self, mx, my, mz, pitch, roll, gz):
    now = time.ticks_ms()
    dt = time.ticks_diff(now, self.last_time) / 1000
    self.last_time = now

    # --- 1. Integrate gyro (yaw) ---
    self.yaw += gz * dt

    # Keep yaw in 0–360
    if self.yaw < 0:
        self.yaw += 360
    elif self.yaw > 360:
        self.yaw -= 360

    # --- 2. Compute magnetometer heading ---
    try:
        mag_heading = tilt_compensated_heading(mx, my, mz, pitch, roll)
    except:
        mag_heading = self.last_heading

    # --- 3. Detect bad magnetometer data ---
    mag_delta = abs(mx - self.prev_mx) + abs(my - self.prev_my)
    rotation_rate = abs(gz)

    self.prev_mx = mx
    self.prev_my = my

    use_mag = True

    # If rotating but mag not changing → bad mag
    if rotation_rate > 5 and mag_delta < 5:
        use_mag = False

    # If tilted too much → bad mag
    if abs(pitch) > 60 or abs(roll) > 60:
        use_mag = False

    # --- 4. Fuse gyro + mag ---
    if use_mag:
        alpha = 0.98
        self.yaw = alpha * self.yaw + (1 - alpha) * mag_heading

    self.last_heading = self.yaw
    return self.yaw
    
class ComplementaryFilter:
    def __init__(self, alpha=0.98):
        self.alpha = alpha
        self.pitch = 0
        self.roll = 0
        self.last_time = time.ticks_ms()

    def update(self, ax, ay, az, gx, gy, gz):
        now = time.ticks_ms()
        dt = (time.ticks_diff(now, self.last_time)) / 1000
        self.last_time = now

        # --- Accelerometer angles ---
        accel_pitch = math.atan2(ay, az) * 180 / math.pi
        accel_roll  = math.atan2(-ax, az) * 180 / math.pi

        # --- Gyro integration ---
        self.pitch += gx * dt
        self.roll  += gy * dt

        # --- Complementary filter ---
        self.pitch = self.alpha * self.pitch + (1 - self.alpha) * accel_pitch
        self.roll  = self.alpha * self.roll  + (1 - self.alpha) * accel_roll

        return self.pitch, self.roll
    
class LowPass:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.value = None

    def update(self, v):
        if self.value is None:
            self.value = v
        else:
            self.value = self.alpha * v + (1 - self.alpha) * self.value
        return self.value

# ────────────── Motor Controller ──────────────
class MotorController:
    def __init__(self):
        self.motor1a = PWM(Pin(0)); self.motor1b = PWM(Pin(1))
        self.motor2a = PWM(Pin(2)); self.motor2b = PWM(Pin(3))
        self.motor3a = PWM(Pin(4)); self.motor3b = PWM(Pin(5))
        self.motor4a = PWM(Pin(6)); self.motor4b = PWM(Pin(7))

        for pwm in [self.motor1a, self.motor1b, self.motor2a, self.motor2b,
                    self.motor3a, self.motor3b, self.motor4a, self.motor4b]:
            pwm.freq(1000)
            pwm.duty_u16(0)

        self.state = {"motor1": 0, "motor2": 0, "motor3": 0, "motor4": 0}

    def wheel_to_pwm(self, wheel_value):
        return max(0, min(100, wheel_value))

    def set_motor(self, m_a, m_b, speed, reverse=False):
        duty = int(speed / 100 * 65535)
        if reverse:
            m_a.duty_u16(0)
            m_b.duty_u16(duty)
        else:
            m_a.duty_u16(duty)
            m_b.duty_u16(0)

        if m_a == self.motor1a: self.state["motor1"] = speed
        elif m_a == self.motor2a: self.state["motor2"] = speed
        elif m_a == self.motor3a: self.state["motor3"] = speed
        elif m_a == self.motor4a: self.state["motor4"] = speed

    def stop_all(self):
        for pwm in [self.motor1a, self.motor1b, self.motor2a, self.motor2b,
                    self.motor3a, self.motor3b, self.motor4a, self.motor4b]:
            pwm.duty_u16(0)

# ────────────── Battery Monitor ──────────────
class BatteryMonitor:
    def __init__(self, pin=29):
        self.adc = ADC(pin)
        self.samples = []

    def read_voltage(self):
        raw = self.adc.read_u16()
        voltage = raw * 3.3 / 65535 * 3
        self.samples.append(voltage)
        if len(self.samples) > 10: self.samples.pop(0)
        return sum(self.samples) / len(self.samples)

    def percent(self, v=None):
        if v is None: v = self.read_voltage()
        if v >= 4.2: return 100
        if v <= 3.3: return 0
        return int((v - 3.3) / (4.2 - 3.3) * 100)

# ────────────── MPU6050 Wrapper ──────────────
class MPU6050Sensor:
    def __init__(self, i2c):
        self.mpu = MPU6050(i2c)

    @property
    def accel(self):
        return self.mpu.accel.xyz

    @property
    def gyro(self):
        return self.mpu.gyro.xyz
    
# ────────────── VL53L0X Wrapper ──────────────
class VL53L0XSensor:
    def __init__(self, i2c):
        
        self.tof = VL53L0X(i2c)

    def read(self):
        try:
            return self.tof.read()  # distance in mm
        except:
            return -1  # error fallback
        
# ────────────── GY271 Wrapper ──────────────
class GY271Sensor:
    def __init__(self, i2c, addr=0x0D):
        self.i2c = i2c
        self.addr = addr
        # Reset
        self.i2c.writeto_mem(addr, 0x0B, b'\x01')
        # Continuous measurement, 200Hz, normal mode
        # 0x09 register: 0b00011101 → Continuous, 200Hz, 2G range, normal mode
        self.i2c.writeto_mem(addr, 0x09, b'\x19')

    def read(self):
        data = self.i2c.readfrom_mem(self.addr, 0x00, 6)
        # little endian, signed
        x = int.from_bytes(data[0:2], 'little', True)
        y = int.from_bytes(data[2:4], 'little', True)
        z = int.from_bytes(data[4:6], 'little', True)

        # --- FIX: handle overflow / wrap ---
        if z > 32767:
            z -= 65536
        return x, y, z
        
# ────────────── BLE Peripheral ──────────────
class BLEPeripheral:
    SERVICE_UUID = bluetooth.UUID("19b10000-e8f2-537e-4f6c-d104768a1214")
    RX_UUID = bluetooth.UUID("19b10001-e8f2-537e-4f6c-d104768a1214")
    TX_UUID = bluetooth.UUID("19b10002-e8f2-537e-4f6c-d104768a1214")

    def __init__(self, motor_controller, battery_monitor, drone=None):
        self.mc = motor_controller
        self.battery = battery_monitor
        self.drone = drone  # store reference to PicoDrone instance

        self.service = aioble.Service(self.SERVICE_UUID)

        self.rx_char = aioble.Characteristic(
            self.service, self.RX_UUID,
            write=True, write_no_response=True, notify=False
        )

        self.tx_char = aioble.Characteristic(
            self.service, self.TX_UUID, read=True, notify=True
        )

        aioble.register_services(self.service)

    async def rx_listener(self):
        while True:
            await self.rx_char.written()
            data = self.rx_char.read()
            if data:
                await self.rx_handler(data)

    async def rx_handler(self, data):
        if len(data) == 1 and data[0] == 0xFF:
            if self.drone:
                self.drone.start_calibration()
                print("Calibration triggered via single byte!")
            return
        if len(data) == 1:
            wheel_value = data[0]
            pwm_speed = self.mc.wheel_to_pwm(wheel_value)
            self.mc.set_motor(self.mc.motor1a, self.mc.motor1b, pwm_speed, reverse=True)
            self.mc.set_motor(self.mc.motor2a, self.mc.motor2b, pwm_speed)
            self.mc.set_motor(self.mc.motor3a, self.mc.motor3b, pwm_speed)
            self.mc.set_motor(self.mc.motor4a, self.mc.motor4b, pwm_speed, reverse=True)
        else:
            try:
                msg = ujson.loads(data)
                key = msg.get("key"); state = msg.get("state")
                if key == "calibrate" and state == True:
                    # Call start_calibration on the PicoDrone instance
                    if self.drone:
                        self.drone.start_calibration()
                        print("Calibration triggered via BLE!")
                print(f"Key command: {key} = {state}")
            except Exception as e:
                print("Failed to parse control payload:", e)

# ────────────── Main PicoDrone App ──────────────
class PicoDrone:
    def __init__(self):
        self.i2c0 = I2C(0, sda=Pin(20), scl=Pin(21), freq=400_000)
        self.motor_controller = MotorController()
        self.battery_monitor = BatteryMonitor()
        self.mpu = MPU6050Sensor(self.i2c0)
        self.vl53 = VL53L0XSensor(self.i2c0)
        self.mag = GY271Sensor(self.i2c0)
        self.ble = BLEPeripheral(self.motor_controller, self.battery_monitor, drone=self)
        self.vsys_enable = Pin(25, Pin.OUT)
        self.vsys_enable.value(1)
        self.filter = ComplementaryFilter()
        self.pitch_filter = LowPass()
        self.roll_filter = LowPass()
        self.mx_filter = LowPass()
        self.my_filter = LowPass()
        self.mz_filter = LowPass()
        self.calibrating = False
        self.calibration_start_time = 0
        self.calibration_duration = 60
        
        # --- Heading fusion ---
        self.yaw = 0
        self.last_heading = 0
        self.prev_mx = 0
        self.prev_my = 0
        self.last_time = time.ticks_ms()

        # Reset complementary filter to zero
        self.filter.pitch = 0
        self.filter.roll = 0
        
        # gy271 min/max
        self.min_x = 999999
        self.max_x = -999999
        self.min_y = 999999
        self.max_y = -999999
        self.min_z = 999999
        self.max_z = -999999

        # Accelerometer min/max
        self.ax_min = 999999
        self.ax_max = -999999
        self.ay_min = 999999
        self.ay_max = -999999
        self.az_min = 999999
        self.az_max = -999999

        # Accelerometer offsets
        self.ax_offset = 0
        self.ay_offset = 0
        self.az_offset = 0
        
        print("I2C0:", self.i2c0.scan())
        
    
        
    def start_calibration(self):
        print("Starting magnetometer calibration...")
        self.calibrating = True
        self.calibration_start_time = time.time()

        # Reset gy271 min/max
        self.min_x = 999999; self.max_x = -999999
        self.min_y = 999999; self.max_y = -999999
        self.min_z = 999999; self.max_z = -999999

        # Reset MPU6050 accel min/max
        self.ax_min = 999999; self.ax_max = -999999
        self.ay_min = 999999; self.ay_max = -999999
        self.az_min = 999999; self.az_max = -999999
        
    
    def update_gy271_calibration(self, mx, my, mz):
        if not self.calibrating:
            return

        self.min_x = min(self.min_x, mx)
        self.max_x = max(self.max_x, mx)
        self.min_y = min(self.min_y, my)
        self.max_y = max(self.max_y, my)
        self.min_z = min(self.min_z, mz)
        self.max_z = max(self.max_z, mz)

        # Stop after duration
        if time.time() - self.calibration_start_time > self.calibration_duration:
            self.calibrating = False
            print("Calibration complete:")
            print(f"X: {self.min_x}-{self.max_x}")
            print(f"Y: {self.min_y}-{self.max_y}")
            print(f"Z: {self.min_z}-{self.max_z}")

    def update_mpu_calibration(self, ax, ay, az):
        """Call each loop while calibrating to compute accel offsets."""
        if not self.calibrating:
            return

        # Track min/max
        self.ax_min = min(self.ax_min, ax)
        self.ax_max = max(self.ax_max, ax)
        self.ay_min = min(self.ay_min, ay)
        self.ay_max = max(self.ay_max, ay)
        self.az_min = min(self.az_min, az)
        self.az_max = max(self.az_max, az)

        # Compute offsets
        self.ax_offset = compute_accel_offsets(self.ax_min, self.ax_max)
        self.ay_offset = compute_accel_offsets(self.ay_min, self.ay_max)
        self.az_offset = compute_accel_offsets(self.az_min, self.az_max, g_axis=True)


    async def run(self):
        print("BLE peripheral ready – MPU6050 streaming")
        while True:
            voltage = self.battery_monitor.read_voltage()
            percent = self.battery_monitor.percent(voltage)
            print("Battery:", voltage, "V", percent, "%")
            
            
            try:
                async with await aioble.advertise(
                    500_000,
                    name="PicoDrone",
                    services=[BLEPeripheral.SERVICE_UUID],
                ) as conn:
                    print("Connected! Connection obj:", conn)
                    await asyncio.sleep_ms(1500)
                    asyncio.create_task(self.ble.rx_listener())

                    while True:
                        ax, ay, az = self.mpu.accel
                        gx, gy, gz = self.mpu.gyro
                        mx, my, mz = self.mag.read()
                        
                        # Apply accelerometer offsets
                        ax -= self.ax_offset
                        ay -= self.ay_offset
                        az -= self.az_offset
                        
                        pitch, roll = self.filter.update(ax, ay, az, gx, gy, gz)
                        
                        
                        
                        # --- FIX: clamp angles ---
                        pitch = max(-90, min(90, pitch))
                        roll  = max(-90, min(90, roll))
                        

                        print("Pitch:", round(pitch,1), "Roll:", round(roll,1))
                        
                        #Get height distance
                        distance = self.vl53.read()
                        #print("Distance:", distance, "mm")
                        
                        if self.calibrating:
                            print("Calibrating... Move the drone in all orientations.")
                            self.update_gy271_calibration(mx, my, mz)
                            self.update_mpu_calibration(ax, ay, az)

                            print("Mag range:",
                            self.max_x - self.min_x,
                            self.max_y - self.min_y,
                            self.max_z - self.min_z)

                        #print("X:", self.min_x, self.max_x)
                        #print("Y:", self.min_y, self.max_y)
                        #print("Z:", self.min_z, self.max_z)
                        #print("mx: " + str(mx) + " my: " + str(my) + " mz: " + str(mz))
                        
                        offset_x = compute_offsets(self.min_x, self.max_x)
                        offset_y = compute_offsets(self.min_y, self.max_y)
                        offset_z = compute_offsets(self.min_z, self.max_z)

                        mx -= offset_x
                        my -= offset_y
                        #mz -= offset_z
                        
                        # scale_x = compute_scale(self.min_x, self.max_x)
                        # scale_y = compute_scale(self.min_y, self.max_y)
                        # scale_z = compute_scale(self.min_z, self.max_z)

                        # avg_scale = (scale_x + scale_y + scale_z) / 3
        

                        # if scale_x != 0:
                        #     mx = mx * (avg_scale / scale_x)

                        # if scale_y != 0:
                        #     my = my * (avg_scale / scale_y)

                        # if scale_z != 0:
                        #     mz = mz * (avg_scale / scale_z)
                        
                        mx = self.mx_filter.update(mx)
                        my = self.my_filter.update(my)
                        #mz = self.mz_filter.update(mz)
                        
                        heading = get_heading(mx, my)
                        #heading = fuse_heading(self, mx, my, mz, pitch, roll, gz)
                        
                        direction = get_cardinal_direction(heading)
                        print("Heading:", round(heading,1), "Direction:", direction)
                        
                        data = struct.pack(
                            "8fB4B",
                            ax, ay, az,
                            gx, gy, gz,
                            heading,
                            distance,
                            self.battery_monitor.percent(),
                            self.motor_controller.state["motor1"],
                            self.motor_controller.state["motor2"],
                            self.motor_controller.state["motor3"],
                            self.motor_controller.state["motor4"]
                        )

                        for _ in range(3):
                            try:
                                await self.ble.tx_char.notify(conn, data)
                                break
                            except Exception:
                                await asyncio.sleep_ms(50)
                        await asyncio.sleep_ms(400)

                    await conn.disconnected()
                    print("Disconnected")

            except Exception as e:
                print("Advertise/conn error:", str(e))
                await asyncio.sleep(1)


if __name__ == "__main__":
    drone = PicoDrone()
    asyncio.run(drone.run())








