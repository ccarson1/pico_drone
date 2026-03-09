# main.py -- BLE + MPU6050 data streaming (motors disabled)

import aioble
import asyncio
import bluetooth
from machine import Pin, PWM, I2C, ADC
import struct
from libs.imu import MPU6050
import time

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

async def rx_listener(rx_char):
    while True:
        await rx_char.written()
        data = rx_char.read()

        if data:
            print("BLE RX:", data)
            await rx_handler(rx_char, data)

async def rx_handler(characteristic, data):
    """Handle incoming control commands from BLE (wheel/key)."""
    if len(data) == 1:
        # Single byte → wheel value
        wheel_value = data[0]
        pwm_speed = wheel_to_pwm(wheel_value)
        print("Wheel command:", wheel_value)
        # TODO: map wheel_value to motor PWM
        # Example for front motors:
        # set_motor(motor1a, motor1b, wheel_value)
        # Set all motors
        set_motor(motor1a, motor1b, pwm_speed)
        set_motor(motor2a, motor2b, pwm_speed)
        set_motor(motor3a, motor3b, pwm_speed) #Front Right
        set_motor(motor4a, motor4b, pwm_speed, reverse=True)#Front Left
    else:
        # Assume JSON payload → key press
        try:
            import ujson
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
                asyncio.create_task(rx_listener(rx_char))

                # Main loop: read MPU6050, send battery + accel/gyro
                while True:
                    ax, ay, az = mpu.accel.xyz
                    gx, gy, gz = mpu.gyro.xyz
                    data = struct.pack(
                        "6fB4B",
                        ax, ay, az,
                        gx, gy, gz,
                        battery_percent(read_battery_voltage()),
                        motor_state["motor1"],
                        motor_state["motor2"],
                        motor_state["motor3"],
                        motor_state["motor4"]
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

