# main.py -- BLE + MPU6050 data streaming (motors disabled)

import aioble
import asyncio
import bluetooth
from machine import Pin, PWM, I2C, ADC
import struct
from lib.imu import MPU6050
import time
import math
import ujson

# ────────────── Pin definitions ──────────────
i2c = I2C(0, sda=Pin(20), scl=Pin(21), freq=400000)

motor1a = PWM(Pin(0))
motor1b = PWM(Pin(1))
motor2a = PWM(Pin(2))
motor2b = PWM(Pin(3))
motor3a = PWM(Pin(4))
motor3b = PWM(Pin(5))
motor4a = PWM(Pin(6))
motor4b = PWM(Pin(7))

pwm_speed = 0
last_time = time.ticks_ms()

# PID state
pitch_integral = 0
roll_integral = 0
last_pitch_error = 0
last_roll_error = 0

# PID constants — tune these experimentally
Kp = 1.0
Ki = 0.0
Kd = 0.05

# MPU offsets
ax_offset = 0
ay_offset = 0
az_offset = 0
gx_offset = 0
gy_offset = 0
gz_offset = 0

# Store last PWM values for each motor
motor_state = {
    "motor1": 0,
    "motor2": 0,
    "motor3": 0,
    "motor4": 0,
}

for pwm in [motor1a, motor1b, motor2a, motor2b, motor3a, motor3b, motor4a, motor4b]:
    pwm.freq(1000)
    pwm.duty_u16(0)

mpu = MPU6050(i2c)

# ────────────── BLE setup ──────────────
SERVICE_UUID = bluetooth.UUID("19b10000-e8f2-537e-4f6c-d104768a1214")
RX_UUID = bluetooth.UUID("19b10001-e8f2-537e-4f6c-d104768a1214")
TX_UUID = bluetooth.UUID("19b10002-e8f2-537e-4f6c-d104768a1214")


service = aioble.Service(SERVICE_UUID)

print("Attributes of Character")
print(dir(aioble.Characteristic))

rx_char = aioble.Characteristic(
    service,
    RX_UUID,
    write=True,
    write_no_response=True,
    notify=False
)

def get_pitch_roll(ax, ay, az):
    pitch = math.atan2(ax, math.sqrt(ay*ay + az*az)) * 180 / math.pi
    roll  = math.atan2(ay, math.sqrt(ax*ax + az*az)) * 180 / math.pi
    return pitch, roll

async def send_status(msg, connection):

    encoded = msg.encode()

    try:
        await tx_char.notify(connection, encoded)
    except:
        pass


async def calibrate_imu(samples=500):

    global ax_offset, ay_offset, az_offset
    global gx_offset, gy_offset, gz_offset

    ax_sum = ay_sum = az_sum = 0
    gx_sum = gy_sum = gz_sum = 0

    print("Keep drone still...")
    
    # discard warm-up samples
    for _ in range(50):
        mpu.accel.xyz
        mpu.gyro.xyz
        await asyncio.sleep_ms(5)

    for i in range(samples):

        ax, ay, az = mpu.accel.xyz
        gx, gy, gz = mpu.gyro.xyz

        ax_sum += ax
        ay_sum += ay
        az_sum += az

        gx_sum += gx
        gy_sum += gy
        gz_sum += gz

        await asyncio.sleep_ms(5)

    ax_offset = ax_sum / samples
    ay_offset = ay_sum / samples
    az_offset = az_sum / samples - 1

    gx_offset = gx_sum / samples
    gy_offset = gy_sum / samples
    gz_offset = gz_sum / samples

    print("Offsets:", ax_offset, ay_offset, az_offset, gx_offset, gy_offset, gz_offset)

async def rx_listener(rx_char, connection):
    while True:
        await rx_char.written()
        data = rx_char.read()

        if data:
            print("BLE RX:", data)
            await rx_handler(rx_char, data, connection)

async def rx_handler(characteristic, data, connection):
    """Handle incoming control commands from BLE (wheel/key)."""
    global pwm_speed
    if len(data) == 1:

        cmd = data[0]

        # CALIBRATE COMMAND
        if cmd == 0xFF:
            print("Calibrating IMU...")

            await send_status("calibrating", connection)

            await calibrate_imu()

            print("Calibration complete")

            await send_status("calibrated", connection)

            return

        # otherwise treat as wheel command
        wheel_value = cmd
        pwm_speed = wheel_to_pwm(wheel_value)

        print("Wheel command:", wheel_value)

        #set_motor(motor1a, motor1b, pwm_speed)
        #set_motor(motor2a, motor2b, pwm_speed)
        #set_motor(motor3a, motor3b, pwm_speed)
        #set_motor(motor4a, motor4b, pwm_speed, reverse=True)
    else:
        # Assume JSON payload → key press
        try:
            
            msg = ujson.loads(data)
            key = msg.get("key")
            state = msg.get("state")
            print(f"Key command: {key} = {state}")
            # TODO: implement key handling (forward/back/turn)
        except Exception as e:
            print("Failed to parse control payload:", e)


tx_char = aioble.Characteristic(service, TX_UUID, read=True, notify=True)
aioble.register_services(service)
vsys_enable = Pin(25, Pin.OUT)
vsys_enable.value(1)
battery_adc = ADC(29)

battery_samples = []


def wheel_to_pwm(wheel_value):
    # Ensure speed is within 0-100
    return max(0, min(100, wheel_value))

def set_motor(m_a, m_b, speed, reverse=False):
    """
    Speed: 0 (stop) to 100 (full forward)
    """
    duty = int(speed / 100 * 65535)
    if reverse:
        m_a.duty_u16(0)
        m_b.duty_u16(duty)
    else:
        m_a.duty_u16(duty)
        m_b.duty_u16(0)

    # Track motor state for front-end
    if m_a == motor1a: motor_state["motor1"] = speed
    elif m_a == motor2a: motor_state["motor2"] = speed
    elif m_a == motor3a: motor_state["motor3"] = speed
    elif m_a == motor4a: motor_state["motor4"] = speed

def stop_all():
    for pwm in [motor1a, motor1b, motor2a, motor2b, motor3a, motor3b, motor4a, motor4b]:
        pwm.duty_u16(0)


def read_battery_voltage():
    raw = battery_adc.read_u16()
    #print("RAW ADC:", raw)
    voltage = raw * 3.3 / 65535 * 3

    battery_samples.append(voltage)
    if len(battery_samples) > 10:
        battery_samples.pop(0)

    return sum(battery_samples) / len(battery_samples)

def battery_percent(v):
    if v >= 4.2:
        return 100
    if v <= 3.3:
        return 0
    return int((v - 3.3) / (4.2 - 3.3) * 100)

async def main():
    print("BLE peripheral ready – MPU6050 streaming")
    
    while True:
        voltage = read_battery_voltage()
        percent = battery_percent(voltage)
        print("Battery:", voltage, "V", percent, "%")
        try:
            async with await aioble.advertise(
                500_000,
                name="PicoDrone",
                services=[SERVICE_UUID],
            ) as connection:
                print("Connected! Connection obj:", connection)

                # Give central time to subscribe
                await asyncio.sleep_ms(1500)

                # Start listening for writes
                asyncio.create_task(rx_listener(rx_char, connection))

                # Main loop: read MPU6050, send battery + accel/gyro
                while True:
                    global last_time, pitch_integral, roll_integral, last_pitch_error, last_roll_error
                    ax, ay, az = mpu.accel.xyz
                    gx, gy, gz = mpu.gyro.xyz

                    ax -= ax_offset
                    ay -= ay_offset
                    az -= az_offset

                    gx -= gx_offset
                    gy -= gy_offset
                    gz -= gz_offset
                    
                    #Compute pitch and roll from accel
                    pitch, roll = get_pitch_roll(ax, ay, az)

                    # dt for PID
                    now = time.ticks_ms()
                    dt = (now - last_time) / 1000
                    last_time = now

                    # Pitch PID
                    pitch_error = 0 - pitch  # desired pitch = 0
                    pitch_integral += pitch_error * dt
                    pitch_derivative = (pitch_error - last_pitch_error) / dt
                    pitch_correction = Kp*pitch_error + Ki*pitch_integral + Kd*pitch_derivative
                    last_pitch_error = pitch_error

                    # Roll PID
                    roll_error = 0 - roll  # desired roll = 0
                    roll_integral += roll_error * dt
                    roll_derivative = (roll_error - last_roll_error) / dt
                    roll_correction = Kp*roll_error + Ki*roll_integral + Kd*roll_derivative
                    last_roll_error = roll_error

                    # Compute motor speeds
                    m1 = pwm_speed + pitch_correction + roll_correction
                    m2 = pwm_speed + pitch_correction - roll_correction
                    m3 = pwm_speed - pitch_correction - roll_correction
                    m4 = pwm_speed - pitch_correction + roll_correction

                    # Clamp 0-100
                    m1 = max(0, min(100, m1))
                    m2 = max(0, min(100, m2))
                    m3 = max(0, min(100, m3))
                    m4 = max(0, min(100, m4))

                    # Set motors
                    set_motor(motor1a, motor1b, m1)
                    set_motor(motor2a, motor2b, m2)
                    set_motor(motor3a, motor3b, m3, reverse=True)
                    set_motor(motor4a, motor4b, m4, reverse=True)
                    
                    
                    data = struct.pack(
                        "6fB4B",
                        ax, ay, az,
                        gx, gy, gz,
                        int(battery_percent(read_battery_voltage())),
                        int(motor_state["motor1"]),
                        int(motor_state["motor2"]),
                        int(motor_state["motor3"]),
                        int(motor_state["motor4"])
                    )
                    
                    for _ in range(3):
                        try:
                            await tx_char.notify(connection, data)
                            break
                        except Exception:
                            await asyncio.sleep_ms(50)
                    await asyncio.sleep_ms(400)
                
                print("Inner loop exited - waiting for disconnect")
                await connection.disconnected()
                print("Disconnected")
                
        except Exception as e:
            print("Advertise/conn error:", str(e))
            await asyncio.sleep(1)

asyncio.run(main())





