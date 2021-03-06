# -*- coding: utf-8 -*-

# Octowire Framework
# Copyright (c) ImmunIT - Jordan Ovrè / Paul Duncan
# License: Apache 2.0
# Paul Duncan / Eresse <pduncan@immunit.ch>
# Jordan Ovrè / Ghecko <jovre@immunit.ch>

import struct
import time

from tqdm import tqdm

from octowire_framework.module.AModule import AModule
from octowire.gpio import GPIO
from octowire.spi import SPI
from owfmodules.avrisp.device_id import DeviceID


class EepromErase(AModule):
    def __init__(self, owf_config):
        super(EepromErase, self).__init__(owf_config)
        self.meta.update({
            'name': 'AVR EEPROM memory erase',
            'version': '1.0.2',
            'description': 'Erase the EEPROM memory of AVR microcontrollers',
            'author': 'Jordan Ovrè / Ghecko <jovre@immunit.ch>, Paul Duncan / Eresse <pduncan@immunit.ch>'
        })
        self.options = {
            "spi_bus": {"Value": "", "Required": True, "Type": "int",
                        "Description": "SPI bus (0=SPI0 or 1=SPI1)", "Default": 0},
            "reset_line": {"Value": "", "Required": True, "Type": "int",
                           "Description": "GPIO used as the Reset line", "Default": 0},
            "spi_baudrate": {"Value": "", "Required": True, "Type": "int",
                             "Description": "SPI frequency (1000000 = 1MHz). Minimum: 240kHz - Maximum: 60MHz",
                             "Default": 1000000},
        }
        self.dependencies.append("owfmodules.avrisp.device_id>=1.0.0")

    def get_device_id(self, spi_bus, reset_line, spi_baudrate):
        device_id_module = DeviceID(owf_config=self.config)
        # Set DeviceID module options
        device_id_module.options["spi_bus"]["Value"] = spi_bus
        device_id_module.options["reset_line"]["Value"] = reset_line
        device_id_module.options["spi_baudrate"]["Value"] = spi_baudrate
        device_id_module.owf_serial = self.owf_serial
        device_id = device_id_module.run(return_value=True)
        return device_id

    @staticmethod
    def wait_poll_eeprom(spi_interface, byte, byte_addr):
        read_cmd = b'\xA0'

        # 10s timeout
        timeout = time.time() + 10

        while True:
            # Send read cmd
            spi_interface.transmit(read_cmd + struct.pack(">H", byte_addr))
            # Receive the byte and compare it
            read_byte = spi_interface.receive(1)[0]
            if read_byte == byte:
                return True
            if time.time() > timeout:
                return False

    def erase(self, spi_interface, reset, device):
        write_cmd = b'\xC0'
        enable_mem_access_cmd = b'\xac\x53\x00\x00'

        # Drive reset low
        reset.status = 0
        self.logger.handle("Enabling Memory Access...", self.logger.INFO)

        # Enable Memory Access
        spi_interface.transmit(enable_mem_access_cmd)
        time.sleep(0.5)

        # Fill the eeprom with 0xFF
        self.logger.handle("Erasing the EEPROM memory (Write 0xFF)...", self.logger.INFO)
        for addr in tqdm(range(0, int(device["eeprom_size"], 16), 1), desc="Erasing", ascii=" #", unit_scale=True,
                         bar_format="{desc} : {percentage:3.0f}%[{bar}] {n_fmt}/{total_fmt} bytes "
                                    "[elapsed: {elapsed} left: {remaining}]"):
            spi_interface.transmit(write_cmd + struct.pack(">H", addr) + b'\xFF')
            # Wait until byte write on the eeprom
            if not self.wait_poll_eeprom(spi_interface, 0xFF, addr):
                self.logger.handle("\nErasing at byte address '{}' took too long, exiting..".format(addr),
                                   self.logger.ERROR)
                return False

        # Drive reset high
        reset.status = 1
        self.logger.handle("EEPROM memory successfully erased.", self.logger.SUCCESS)
        return True

    def process(self):
        spi_bus = self.options["spi_bus"]["Value"]
        reset_line = self.options["reset_line"]["Value"]
        spi_baudrate = self.options["spi_baudrate"]["Value"]

        device = self.get_device_id(spi_bus, reset_line, spi_baudrate)
        if device is None:
            return

        spi_interface = SPI(serial_instance=self.owf_serial, bus_id=spi_bus)
        reset = GPIO(serial_instance=self.owf_serial, gpio_pin=reset_line)

        # Configure SPI with default phase and polarity
        spi_interface.configure(baudrate=spi_baudrate)
        # Configure GPIO as output
        reset.direction = GPIO.OUTPUT

        # Reset is active-low
        reset.status = 1

        # Erase the target chip
        return self.erase(spi_interface, reset, device)

    def run(self, return_value=False):
        """
        Main function.
        Erase the EEPROM memory of an AVR device.
        :return: Bool if return_value is true, else nothing.
        """
        # If detect_octowire is True then detect and connect to the Octowire hardware. Else, connect to the Octowire
        # using the parameters that were configured. This sets the self.owf_serial variable if the hardware is found.
        self.connect()
        if not self.owf_serial:
            return
        try:
            status = self.process()
            if return_value:
                return status
        except ValueError as err:
            self.logger.handle(err, self.logger.ERROR)
        except Exception as err:
            self.logger.handle("{}: {}".format(type(err).__name__, err), self.logger.ERROR)
