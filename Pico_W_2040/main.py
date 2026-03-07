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

for pwm in [motor1a, motor1b, motor2a, motor2b, motor3a, motor3b, motor4a, motor4b]:
    pwm.freq(1000)
    pwm.duty_u16(0)

mpu = MPU6050(i2c)

# ────────────── BLE setup ──────────────
SERVICE_UUID = bluetooth.UUID("19b10000-e8f2-537e-4f6c-d104768a1214")
RX_UUID = bluetooth.UUID("19b10001-e8f2-537e-4f6c-d104768a1214")
TX_UUID = bluetooth.UUID("19b10002-e8f2-537e-4f6c-d104768a1214")


service = aioble.Service(SERVICE_UUID)
rx_char = aioble.Characteristic(service, RX_UUID, write=True, write_no_response=True)
tx_char = aioble.Characteristic(service, TX_UUID, read=True, notify=True)
aioble.register_services(service)
battery_adc = ADC(29)
vsys_enable = Pin(25, Pin.OUT)
vsys_enable.value(1)
battery_samples = []

def set_motor(m_a, m_b, speed):
    pass

def stop_all():
    pass


def read_battery_voltage():
    raw = battery_adc.read_u16()
    print("RAW ADC:", raw)
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
                
                await asyncio.sleep_ms(1000)
                
                last_notify_time = 0
                
                while True:
                    try:
                        ax, ay, az = mpu.accel.xyz
                        gx, gy, gz = mpu.gyro.xyz
                        
                        #print(f"Local read: Acc {ax:.2f} {ay:.2f} {az:.2f} | Gyro {gx:.2f} {gy:.2f} {gz:.2f}")
                        
                        
                        
                        data = struct.pack("6fB", ax, ay, az, gx, gy, gz, percent)
                        print(data)
                        
                        try:
                            await tx_char.notify(connection, data)
                            #print("Notify sent OK (24 bytes)")
                            
                        except Exception as notify_e:
                            #print("Notify failed this time:", str(notify_e))
                            # Continue anyway - don't break
                            pass
                        
                        last_notify_time = time.ticks_ms()
                        
                        

                        
                        
                    except Exception as e:
                        print("Sensor read error:", str(e))
                        break
                    
                    await asyncio.sleep_ms(400)
                
                print("Inner loop exited - waiting for disconnect")
                await connection.disconnected()
                print("Disconnected")
                
        except Exception as e:
            print("Advertise/conn error:", str(e))
            await asyncio.sleep(1)

asyncio.run(main())
